import os
from dotenv import load_dotenv

load_dotenv()

SP_API_CREDENTIALS = {
    "refresh_token": os.getenv("SP_API_REFRESH_TOKEN"),
    "lwa_app_id": os.getenv("SP_API_LWA_APP_ID"),
    "lwa_client_secret": os.getenv("SP_API_LWA_CLIENT_SECRET"),
    "aws_access_key": os.getenv("SP_API_AWS_ACCESS_KEY"),
    "aws_secret_key": os.getenv("SP_API_AWS_SECRET_KEY"),
    "role_arn": os.getenv("SP_API_ROLE_ARN"),
}

MARKETPLACE_ID = os.getenv("MARKETPLACE_ID", "ATVPDKIKX0DER")
