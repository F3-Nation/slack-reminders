import mysql.connector
import os
from slack_sdk import WebClient
from slack.errors import SlackApiError
from datetime import datetime
import re
import time

import logging

from google.cloud.sql.connector import Connector, IPTypes
import pg8000

from sqlalchemy import create_engine
import pandas as pd

class EmergencyContactHandler:
	def __init__(self):
		pass

	def _get_conn() -> pg8000.dbapi.Connection:
		"""
		Establishes a connection to the PostgreSQL database using the Google Cloud SQL Connector.

		Returns:
			pg8000.dbapi.Connection: A connection object to the PostgreSQL database.
		"""
		
		with Connector() as connector:
			conn: pg8000.dbapi.Connection = connector.connect(
				os.environ["INSTANCE_CONNECTION_NAME"],
				"pg8000",
				user=os.environ["DB_USER"],
				password=os.environ["DB_PASS"],
				db=os.environ["DB_NAME"],
				ip_type=IPTypes.PUBLIC,
			)
			return conn

	def _get_settings() -> pd.DataFrame:
		logging.info("Getting settings")

		pool = create_engine(
			"postgresql+pg8000://", 
			creator=EmergencyContactHandler._get_conn
		)

		query = """
			select 
				team_id,
				workspace_name,
				bot_token,
				settings ->> 'paxminer_database_name' as paxminer_database_name,
				settings ->> 'log_channel_id' as log_channel_id,
				(settings ->> 'reminder_emergencycontact_field') as field,
				(settings ->> 'reminder_emergencycontact_regex') as regex,
				(settings ->> 'reminder_emergencycontact_lookback_days')::numeric::int as lookback_days,
				(settings ->> 'reminder_emergencycontact_notification_day_of_week')::numeric::int as notification_day_of_week,
				(settings ->> 'reminder_emergencycontact_help_message') as help_message
			from 
				slack_spaces
			where 
				(settings ->> 'reminder_emergencycontact_is_active')::bool and
				team_id  is not null and 
				bot_token is not null and
				jsonb_typeof(settings -> 'paxminer_database_name') = 'string' and 
				jsonb_typeof(settings -> 'reminder_emergencycontact_field') = 'string' and 
				settings ->> 'reminder_emergencycontact_field' in ('title', 'real_name', 'display_name', 'phone') and
				jsonb_typeof(settings -> 'reminder_emergencycontact_regex') = 'string' and 
				jsonb_typeof(settings -> 'reminder_emergencycontact_lookback_days') = 'number' and 
				jsonb_typeof(settings -> 'reminder_emergencycontact_notification_day_of_week') = 'number' and
				jsonb_typeof(settings -> 'reminder_emergencycontact_help_message') = 'string'
			"""

		with pool.connect() as db_conn:
			settings = pd.read_sql_query(query, db_conn, None)

		return settings

	def _get_block_header(message):
		return {
			"type": "header",
			"text": {
				"type": "plain_text",
				"text": message
			}
		}

	def _get_block_context(message):
		return {
			"type": "context",
			"elements": [
				{
					"type": "plain_text",
					"text": message
				}
			]
		}

	def _get_block_section(message):
		return {
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": message
			}
		}

	def check_for_missing_emergency_contacts():
		logging.info("Starting")

		settings = EmergencyContactHandler._get_settings()

		for slackWorkspaceInputs in settings.itertuples(index=False):
			try:
				paxMinerDatabase = slackWorkspaceInputs.paxminer_database_name
				workspaceId = slackWorkspaceInputs.team_id
				logChannelId = slackWorkspaceInputs.log_channel_id
				lookback_days = slackWorkspaceInputs.lookback_days
				field = slackWorkspaceInputs.field
				regex = slackWorkspaceInputs.regex
				channelTriggerDay = int(slackWorkspaceInputs.notification_day_of_week) # The day of the week AO and Site Q alerts go out. Monday is 0.
				helpMessage = slackWorkspaceInputs.help_message
				slackToken = slackWorkspaceInputs.bot_token

				# Only run on configured week day
				if datetime.today().weekday() != channelTriggerDay:
					logging.info("Skipping " + paxMinerDatabase + " because it is not the configured day of the week.")
					continue
				
				logging.info("Starting to process " + paxMinerDatabase)

				logging.info("Connecting to Slack and querying users.")
				slack_client = WebClient(token=slackToken)
				try:
					slack_users = slack_client.users_list()
				except SlackApiError as e:
					if e.response['ok'] is False and e.response['error'] == 'ratelimited':
						logging.warning("Rate limited by Slack API. Waiting for 30 seconds before retrying...")
						time.sleep(30)

				logging.info("Connecting to PAXminer database and querying recent users.")
				mydb = mysql.connector.connect(
					host= os.getenv("paxMinerSqlServer"),
					user= os.getenv("paxMinerUsername"),
					password= os.getenv("paxMinerPassword"),
					database= paxMinerDatabase
				)

				cursor = mydb.cursor()
				cursor.execute("""
				    SELECT DISTINCT user_id 
					FROM bd_attendance ba 
					WHERE ba.`date` > (NOW() - INTERVAL """ + str(lookback_days) + """ DAY )"""
				)
				data = cursor.fetchall()

				user_ids = {row[0] for row in data}
				filtered_slack_users = [user for user in slack_users.data["members"] if user["id"] in user_ids]
				logging.info("PAXminer query returned "+ str(len(data)) + " users, which were matched to " + str(len(filtered_slack_users)) + " Slack users.")

				offenders = []
				for user in filtered_slack_users:
					pattern = re.compile(regex, re.IGNORECASE)
					
					if user['profile'][field] is None or user['profile'][field] == "" or not pattern.match(user['profile'][field]):
						offenders.append(user['id'])
						
						message = []
						message.append(EmergencyContactHandler._get_block_header("Emergency Contact Info Missing!"))
						message.append(EmergencyContactHandler._get_block_context("It looks like your emergency contact information is missing. :grimacing:"))
						message.append(EmergencyContactHandler._get_block_section("Please update your emergency contact information in Slack."))
						message.append(EmergencyContactHandler._get_block_section(helpMessage))
						slack_client.chat_postMessage(channel=user["id"], text="Emergency Contact Info Missing!!! :grimacing:", blocks=message, unfurl_links=True)
						logging.info("Messaged user " + user["id"])

				if logChannelId != "" and not logChannelId.isspace():
					if len(offenders) == 0:
						slack_client.chat_postMessage(channel=logChannelId, text="All users have compliant emergency contacts listed. :white_check_mark:")
					else:
						slack_client.chat_postMessage(channel=logChannelId, text="There were " + str(len(offenders)) + " people that do not have compliane emergency contacts listed. They were each sent Slack messages.\n\n<@" + ">,<@".join(offenders) + ">")
			
			except Exception as err:
				logging.info("Failed to process region with inputs '" + str(slackWorkspaceInputs) + "'. Will move to next region. Error:\n\n" + str(err))
				
		logging.info("Finished")