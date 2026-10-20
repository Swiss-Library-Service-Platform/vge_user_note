import logging
import os
from pathlib import Path
import time

import pandas as pd
from dotenv import load_dotenv
from prometheus_client import CollectorRegistry, Gauge, pushadd_to_gateway
from prometheus_client.exposition import basic_auth_handler

from almapiwrapper.analytics import AnalyticsReport
from almapiwrapper.configlog import config_log
from almapiwrapper.users import User, fetch_users, check_synchro


class JobErrors(logging.Handler):
    """Remember errors that the wrapper logs without raising an exception."""

    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.observed = False

    def emit(self, record):
        self.observed = True


def check_users(result):
    report = AnalyticsReport(
        path="/shared/Genève Ville 41SLSP_VGE/Reports/SLSP_VGE_reports_on_request/SUPPORT-43416",
        zone="VGE",
    )
    df_analytics = report.data
    if not isinstance(df_analytics, pd.DataFrame) or "Primary Identifier" not in df_analytics:
        raise ValueError("Analytics report is missing the Primary Identifier column")

    users = fetch_users(
        q="primary_id~@eduid.ch AND note_text~abonum",
        zone="VGE",
        env="P",
    )
    df_api = pd.DataFrame({"primary_id": [user.primary_id for user in users]})
    df_analytics_only = df_analytics[
        ~df_analytics["Primary Identifier"].isin(df_api["primary_id"])
    ]
    logging.info("In Analytics but not in API:\n%s", df_analytics_only.to_string(index=False))

    users = [User(primary_id, "NZ") for primary_id in df_analytics_only["Primary Identifier"]]
    result["candidate_users"] = len(users)
    logging.info("Users to check: %s", users)

    # An empty selection needs no synchronization test (or five-minute wait).
    errors = check_synchro(users) if users else []
    if errors is None:
        raise RuntimeError("Synchronization check did not return a result")
    # These are IZ accounts, not NZ users. There is no reliable success count.
    result["unsynchronized_accounts"] = len(errors)


def publish_result(result):
    gateway = os.getenv("PUSHGATEWAY_URL")
    if not gateway:
        logging.info("PUSHGATEWAY_URL not set; skipping metrics")
        return
    username = os.environ["PUSHGATEWAY_USERNAME"]
    password = os.environ["PUSHGATEWAY_PASSWORD"]

    def auth_handler(url, method, timeout, headers, data):
        return basic_auth_handler(
            url, method, timeout, headers, data, username=username, password=password
        )

    descriptions = {
        "last_run_timestamp_seconds": "Time the latest run ended, including failed runs.",
        "duration_seconds": "Run duration, excluding metrics publication.",
        "candidate_users": "NZ users selected for checking; NaN if unknown.",
        "unsynchronized_accounts": "Unsynchronized IZ accounts reported; NaN if unknown.",
        "execution_completed": "Whether selection and synchronization returned normally.",
        "errors_observed": "Whether execution raised or logged an error; results may be incomplete.",
    }
    registry = CollectorRegistry()
    for name, description in descriptions.items():
        Gauge("vge_user_note_" + name, description, registry=registry).set(result[name])
    pushadd_to_gateway(
        gateway, job="vge_user_note", registry=registry, handler=auth_handler, timeout=15
    )


def main():
    config_log()
    load_dotenv(Path(__file__).with_name(".env.pushgateway"))
    result = {
        "candidate_users": float("nan"),
        "unsynchronized_accounts": float("nan"),
        "execution_completed": 0,
    }
    errors = JobErrors()
    logger = logging.getLogger()
    logger.addHandler(errors)
    started = time.monotonic()
    exit_code = 0
    try:
        check_users(result)
        result["execution_completed"] = 1
    except SystemExit as exc:
        # The wrapper can call sys.exit() after API failures.
        logging.error("Wrapper stopped the job (exit code %s)", exc.code)
        exit_code = 1
    except Exception:
        logging.exception("User synchronization check failed")
        exit_code = 1
    finally:
        logger.removeHandler(errors)
        result["errors_observed"] = int(errors.observed)
        result["duration_seconds"] = time.monotonic() - started
        result["last_run_timestamp_seconds"] = time.time()
        try:
            publish_result(result)
        except Exception:
            # Do not log the request or credentials.
            logging.error("Could not publish job metrics to Pushgateway")
            exit_code = 1

    return exit_code or int(errors.observed)


if __name__ == "__main__":
    raise SystemExit(main())
