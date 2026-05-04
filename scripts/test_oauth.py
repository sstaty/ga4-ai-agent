from google.oauth2.credentials import Credentials
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Metric

creds = Credentials.from_authorized_user_file("oauth_token.json")
client = BetaAnalyticsDataClient(credentials=creds)

request = RunReportRequest(
    property="properties/361414735",
    date_ranges=[DateRange(start_date="7daysAgo", end_date="today")],
    metrics=[Metric(name="sessions")]
)

response = client.run_report(request)
print(response)