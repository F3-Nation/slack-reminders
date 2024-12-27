import mysql.connector
import os
from slack_sdk import WebClient
from operator import itemgetter
from itertools import groupby
from datetime import datetime

from google.cloud.sql.connector import Connector, IPTypes
import pg8000

from sqlalchemy import create_engine
import pandas as pd

connector = Connector()
def getconn() -> pg8000.dbapi.Connection:
	conn: pg8000.dbapi.Connection = connector.connect(
		os.environ["INSTANCE_CONNECTION_NAME"],
		"pg8000",
		user=os.environ["DB_USER"],
		password=os.environ["DB_PASS"],
		db=os.environ["DB_NAME"],
		ip_type=IPTypes.PUBLIC,
	)
	return conn

def GetBlockHeader(message):
	return {
		"type": "header",
		"text": {
			"type": "plain_text",
			"text": message
		}
	}

def GetBlockContext(message):
	return {
		"type": "context",
		"elements": [
			{
				"type": "plain_text",
				"text": message
			}
		]
	}

def GetBlockSection(message):
	return {
		"type": "section",
		"text": {
			"type": "mrkdwn",
			"text": message
		}
	}

def checkForMissingBackblasts(request):
	print("Starting")

	pool = create_engine(
		"postgresql+pg8000://",
		creator=getconn
	)

	query = """
		select
			team_id,
			workspace_name,
			bot_token,
			settings ->> 'paxminer_database_name' as paxminer_database_name,
			settings ->> 'log_channel_id' as log_channel_id,
			coalesce(settings ->> 'reminder_backblast_grace_period_days', '2')::int as grace_period_days,
			coalesce(settings ->> 'reminder_backblast_max_notification_days', '75')::int as max_notification_days,
			coalesce(settings ->> 'reminder_backblast_notification_day_of_week', '0')::int as notification_day_of_week
		from
			slack_spaces"""

	with pool.connect() as db_conn:
		settings = pd.read_sql_query(query, db_conn, None)

	# SQL Query Columns
	indexQ = 4
	indexAO = 5
	indexSiteQ = 6

	for i, slackWorkspaceInputs in settings.iterrows():
		try:
			paxMinerDatabase = slackWorkspaceInputs['paxminer_database_name']
			workspaceId = slackWorkspaceInputs['team_id']
			logChannelId = slackWorkspaceInputs['log_channel_id']
			notificationGracePeriodDays = slackWorkspaceInputs['grace_period_days']
			notificationCutoffDays = slackWorkspaceInputs['max_notification_days']
			channelTriggerDay = int(slackWorkspaceInputs['notification_day_of_week']) # The day of the week AO and Site Q alerts go out. Monday is 0.
			slackToken = slackWorkspaceInputs['bot_token']

			print("Starting " + paxMinerDatabase)

			client = WebClient(token=slackToken)

			mydb = mysql.connector.connect(
				host= os.getenv("paxMinerSqlServer"),
				user= os.getenv("paxMinerUsername"),
				password= os.getenv("paxMinerPassword"),
				database= paxMinerDatabase
			)

			print("Executing query")
			cursor = mydb.cursor()
			cursor.execute("""
				SELECT
					qmbd.event_date AS BD_Date,
					qmbd.event_time AS BD_TIME,
					LEFT(qmbd.event_day_of_week, 3) AS BD_DAY,
					qmbd.event_type AS BD_TYPE,
					COALESCE (qmbd.q_pax_id, "") AS Q,
					qmbd.ao_channel_id AS AO,
					aos.site_q_user_id  AS SiteQ
				FROM
					(
					SELECT
						*
					FROM
						f3stcharles.qsignups_master qm
					WHERE
						NOT EXISTS
						(
						SELECT
							*
						FROM
							""" + paxMinerDatabase + """.beatdowns bd
						WHERE
							qm.ao_channel_id = bd.ao_id
							AND qm.event_date = bd.bd_date )
						AND qm.team_id = '""" + workspaceId + """'
						AND qm.event_date > (NOW() - INTERVAL """ + str(notificationCutoffDays) + """ DAY )
						AND qm.event_date < (NOW() - INTERVAL """ + str(notificationGracePeriodDays) + """ DAY)
					ORDER BY
						qm.event_date,
						qm.event_time) qmbd
				LEFT JOIN
				(
					SELECT
						*
					FROM
						""" + paxMinerDatabase + """.aos) aos
				ON
					qmbd.ao_channel_id = aos.channel_id
				ORDER BY
					qmbd.event_date,
					qmbd.event_time
			""")
			data = cursor.fetchall()

			print("Missing backblasts found: "+ str(len(data)))
			
			if logChannelId != "" and not logChannelId.isspace():
				client.chat_postMessage(channel=logChannelId, text="There are " + str(len(data)) + " missing backblasts as of today (checked between " + str(notificationGracePeriodDays) + " and " + str(notificationCutoffDays) + " days ago).")
			
			if len(data) == 0:
				continue

			# Daily Q Reminder
			dataSorted = [item for item in data if item[indexQ] != '']
			dataSorted.sort(key=itemgetter(indexQ))
			qs = []
			for k,g in groupby(dataSorted, itemgetter(indexQ)):
				qs.append(list(g))

			for q in qs:
				message = []
				message.append(GetBlockHeader("Missing Backblasts!"))
				message.append(GetBlockContext("It looks like you forgot to post the following backblast(s). :grimacing:"))
				qId = q[0][indexQ]
				
				for missingBB in q:
					message.append(GetBlockSection("A " + missingBB[3] + " at <#" + missingBB[indexAO] + "> on " + missingBB[0].strftime("%A") + " " + missingBB[0].strftime("%m/%d/%y") + " at " + missingBB[1]))

				client.chat_postMessage(channel=qId, text="Missing Backblast!!! :grimacing:", blocks=message)
				print("Messaged Q "+ qId)

			# The rest of the reminders are only weekly
			if datetime.today().weekday() != channelTriggerDay:
				print("Not site notification day")
				continue

			# Site Q Reminder
			dataSorted = [item for item in data if item[indexSiteQ] is not None and item[indexSiteQ] != '']
			dataSorted.sort(key=itemgetter(indexSiteQ))
			siteQs = []
			for k,g in groupby(dataSorted, itemgetter(indexSiteQ)):
				siteQs.append(list(g))

			for siteQ in siteQs:
				message = []
				message.append(GetBlockHeader("Missing Backblasts!"))
				message.append(GetBlockContext("It looks like there are backblasts missing at the site(s) you lead. :warning:"))
				siteQId = siteQ[0][indexSiteQ]
				
				for missingBB in siteQ:
					messagePart = "A " + missingBB[3] + " at <#" + missingBB[indexAO] + "> on " + missingBB[0].strftime("%A") + " " + missingBB[0].strftime("%m/%d/%y") + " at " + missingBB[1]
					if (missingBB[indexQ] != ''):
						messagePart = messagePart + (" (<@" + missingBB[indexQ] + "> was Q)")
					message.append(GetBlockSection(messagePart))

				client.chat_postMessage(channel=siteQId, text="Missing Backblasts at your AO! :warning:", blocks=message)
				print("Messaged Site Q " + siteQId)

			# Channel Reminder
			data.sort(key=itemgetter(indexAO))
			aos = []
			for k,g in groupby(data, itemgetter(indexAO)):
				aos.append(list(g))

			for ao in aos:
				message = []
				message.append(GetBlockHeader("Missing Backblasts!"))
				message.append(GetBlockContext("It looks like there are backblasts missing at this AO. :exploding_head:"))
				aoId = ao[0][indexAO]
				
				for missingBB in ao:
					messagePart = "A " + missingBB[3] + " on " + missingBB[0].strftime("%A") + " " + missingBB[0].strftime("%m/%d/%y") + " at " + missingBB[1]
					if (missingBB[indexQ] != ''):
						messagePart = messagePart + (" (<@" + missingBB[indexQ] + "> was Q)")
					message.append(GetBlockSection(messagePart))

				client.chat_postMessage(channel=aoId, text="Missing Backblasts at this AO! :exploding_head:", blocks=message)
				print("Messaged AO " + aoId)
		
		except Exception as err:
			print("Failed to process region with inputs '" + slackWorkspaceInputs + "'. Will move to next region. Error:\n\n" + str(err))
			
	return 'OK'

checkForMissingBackblasts(None)