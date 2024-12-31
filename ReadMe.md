# Slack Reminders
Scripts used to remind Slack users of their commitments. Reminder modes are:
- Backblasts: Compares QSignups to posted backblasts and let PAX/channels know when backblasts are missing.
- Emergency Contact: Messages recent PAX on a weekly basis if they do not have an emergency contact listed on their Slack profile.

The app is run as a web service. Actions are triggered by POSTing to specific endpoints.

## Backblasts

### Prerequisites
You must already have PAXminer, Weaslebot, and QSignups installed for this to work.

### Installation
Gather all of the Inputs listed below (all 8) and email them to tackle@f3nation.com.

### Activating
> [POST] /backblasts

### Process
The app will take a list of Slack Workspaces and iterate through them. It will query PAXminer and QSignups during a specified time period and check to see if any backblasts are missing. The app will group by Q (if available from QSignups) and send a message detailing which backblasts are missing in a direct message. Then it will check the day of the week. If the current day of the week is the one configured for that workspace, it will group missing backblasts by SiteQ if available from the PAXminer `aos` table and send an alert detailing the missing backblasts to the Site Q in a direct message. It will then group missing backblasts by AO and message the AO channel detailing which ones are missing.

### Inputs
Parameters for each Slack Workspace are stored in the F3 Data Model (https://f3-nation.github.io/F3-Data-Models/). Specifically, the `slack_spaces` table. Each entry requires the following fields to be filled in `team_id`, `bot_token`, `settings`. `settings` is a JSON field. It can have properties in it associated with other apps, but it needs at least the following properties to be considered by this app.

```
{
  "log_channel_id": "C082N3FS123",
  "paxminer_database_name": "f3kcwestside",
  "reminder_backblast_is_active": true,
  "reminder_backblast_grace_period_days": 1,
  "reminder_backblast_max_notification_days": 75,
  "reminder_backblast_notification_day_of_week": 1
}
```

1. paxminer_database_name
    - See Common Inputs below
1. team_id
    - See Common Inputs below
1. log_channel_id
    - See Common Inputs below
1. bot_token
    - See Common Inputs below
1. reminder_backblast_is_active
    - A way for system admins to disable the app for a region without deleting the configuration
    - Options are: true, false
1. reminder_backblast_grace_period_days
    - How many days do you want to give a Q to post before messaging them?
    - Example: If this is set to 0, they will be notified right away. For example, if they Q at 5:30 AM and they do not post the backblast by the time the app runs at 9 AM, then they will be notified.
    - Example: If this is set to 1, they have 1 day to post their backblast. If they Q at 5:30 AM on Monday and they haven't posted their backblast by the time the app runs at 9 AM, they won't be notified. But if they still haven't posted by the time the app runs at 9 AM on Tuesday, they will be notified.
    - This can be any positive integer.
1. reminder_backblast_max_notification_days
    - How long should a Q be notified before giving up?
    - Example: If this is set to 75, the app will notify the Q of a missing backblast every time the app runs until more than 75 days have passed since the Q.
    - This can be any positive integer.
1. reminder_backblast_notification_day_of_week
    - A Q will be notified every time the app runs if they don't post. To prevent alarm fatigue on the Site Q and AO, they will only be notified one day a week.
    - The number for the variable represents the day of the week Site Q and AO should be notified. 0 is Monday and 6 is Sunday.
    

### Logging
Basic logs are written for progress updates and actions. If a channel ID is specified in the common inputs, a message will also be posted there for each run.

## Emergency Contact

### Prerequisites
You must already have PAXminer.

### Installation
Gather all of the Inputs listed below (all 10) and email them to tackle@f3nation.com.

### Activating
> [POST] /emergencycontacts

### Process
The app will take a list of Slack Workspaces and iterate through them. If it is not the day the region is configured to be run, it will stop processing that region. It will query all users from Slack, then it will query all users in PAXminer that have posted in the recent past. It will tie the two user lists together using the Slack User ID. The app will compare a configured profile field against a configured regex pattern. If it does not match, it will send the user a configured message asking them to update their profile to include an emergency contact.

### Inputs
Parameters for each Slack Workspace are stored in the F3 Data Model (https://f3-nation.github.io/F3-Data-Models/). Specifically, the `slack_spaces` table. Each entry requires the following fields to be filled in `team_id`, `bot_token`, `settings`. `settings` is a JSON field. It can have properties in it associated with other apps, but it needs at least the following properties to be considered by this app.

```
{
  "log_channel_id": "C04R36F5YGJ",
  "paxminer_database_name": "f3denver",
  "reminder_emergencycontact_field": "title",
  "reminder_emergencycontact_regex": "(?=.*(?:ice|emergency contact))(?=(?:.*\\d){10}).*",
  "reminder_emergencycontact_is_active": true,
  "reminder_emergencycontact_lookback_days": 30,
  "reminder_emergencycontact_notification_day_of_week": 1,
  "reminder_emergencycontact_help_message": "The 'title' field in your Slack profile needs to include an emergency contact phone number. Specifically, the word 'ICE' followed by 10 numbers. For instance 'ICE: 555-867-5309'. Please update your profile following <https://slack.com/intl/en-gb/help/articles/204092246-Edit-your-profile|these instructions>. You will get this message once a week until the phone number is added. Don't be a John Doe!"
}
```

1. paxminer_database_name
    - See Common Inputs below
1. team_id
    - See Common Inputs below
1. log_channel_id
    - See Common Inputs below
1. bot_token
    - See Common Inputs below
1. reminder_emergencycontact_is_active
    - A way for system admins to disable the app for a region without deleting the configuration
    - Options are: true, false
1. reminder_emergencycontact_field
    - This allows you to control which field your users need to have their emergency contact listed in
    - Case-sensative options are: 'title', 'real_name', 'display_name', 'phone'
1. reminder_emergencycontact_regex
    - This is the pattern that the above field must match
    - RegEx is a language/technique for searching for certain patters in strings
    - You can go to [RegExR](https://regexr.com/) to learn about RegEx and test patterns
    - As an example, the pattern "(?=.*(?:ice|emergency contact))(?=(?:.*\\d){10}).*" will match any string that has the word "ICE" or "Emergency Contact" in it AND has 10 digits anywhere in the string.
    - RegEx is not case sensative for this application
1. reminder_emergencycontact_lookback_days
    - The app will only message users that have posted recently
    - This is to not spam accounts of people that are downrange or have quit
    - The app will look back in the PAXminer backblast history this many days to see who has posted in that time frame
    - It will only message people who have posted in the time frame and who don't have a matching emergency contact
1. reminder_emergencycontact_notification_day_of_week
    - To prevent alarm fatigue users with missing emergency contacts will only be notified one day a week
    - The number for the variable represents the day of the week of the notification. 0 is Monday and 6 is Sunday.
1. reminder_emergencycontact_help_message
    - Since every region is different, the app allows admins to specify the message users get.
    - The message needs to explain to people why they are getting the message and how to fix the issue.
    - The example above is probably a good starting point for most regions.


## Common Inputs
- paxminer_database_name
    - The name of the workspace's PAXminer database (e.g. f3denver, f3alliance)
    - This is also used to designate operations in the logs
- team_id
    - The Slack-defined ID for your workspace (see https://docs.louply.io/how-tos/how_to_get_slack_workspace_id/ for instructions on finding it.)
- log_channel_id
    - The Slack-defined ID of a channel you want this app to write logs to. This is useful for troubleshooting. It will write messages to this channel every time it runs and indicate what it found and did.
    - You can use the #paxminer_logs channel or another channel. Generally, it should be a channel not commonly used by users. You will most likely end up muting this channel.
    - See https://help.socialintents.com/article/148-how-to-find-your-slack-team-id-and-slack-channel-id for instructions on finding a Channel ID
    - If this is set left empty (e.g. ",,") then no logs will be written
 bot_token
    - For this app to interact with Slack, it will need certain permissions.
    - You will have to have a custom app installed in your workspace and grant that app the required permissions.
    - You can use an existing app (like PAXminer), or create a new one.
    - https://medium.com/applied-data-science/how-to-build-you-own-slack-bot-714283fd16e5 has a basic run-through of creating an app.
    - When you get to the part about assigning bot token scopes, select
        - chat:write
        - chat:write.public
        - users:read
    - You can get the Bot User OAuth Token from the top of the page where you assign scopes.