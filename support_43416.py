# Import libraries
from almapiwrapper.users import User, NewUser, fetch_users, fetch_user_in_all_iz, Fee, Loan, Request, check_synchro, force_synchro
from almapiwrapper.inventory import IzBib, NzBib, Holding, Item, Collection
from almapiwrapper.config import RecSet, ItemizedSet, LogicalSet, NewLogicalSet, NewItemizedSet, Job, Library, Location, Desk, fetch_libraries
from almapiwrapper.config import Reminder, Library, Location, OpenHours, Department, Letter, IntegrationProfile
from almapiwrapper.config import fetch_reminders, fetch_departments, fetch_libraries
from almapiwrapper.record import JsonData, XmlData
from almapiwrapper.analytics import AnalyticsReport
from almapiwrapper.acquisitions import POLine, Vendor, Invoice, fetch_invoices
from almapiwrapper.configlog import config_log
from almapiwrapper import ApiKeys

import pandas as pd
import json
import logging


# Config logs
config_log()

report = AnalyticsReport(
    path="/shared/Genève Ville 41SLSP_VGE/Reports/SLSP_VGE_reports_on_request/SUPPORT-43416",
    zone="VGE",
)

df_analytics = report.data

users = fetch_users(
    q="primary_id~@eduid.ch AND note_text~abonum",
    zone="VGE",
    env="P",
)

df_api = pd.DataFrame({"primary_id": [user.primary_id for user in users]})

# In Analytics but not in API
df_analytics_only = df_analytics[
    ~df_analytics["Primary Identifier"].isin(df_api["primary_id"])
]
logging.info("In Analytics but not in API:\n%s", df_analytics_only.to_string(index=False))

users = [
    User(primary_id, "NZ")
    for primary_id in df_analytics_only["Primary Identifier"]
]

#users = users[1:]
logging.info("Users to check: %s", users)

errors = check_synchro(users)

