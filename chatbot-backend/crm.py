import os, logging
from crm_integrations import clevertap, braze

logger = logging.getLogger(__name__)

USE_CLEVERTAP = bool(os.getenv("CLEVERTAP_ACCOUNT_ID") and os.getenv("CLEVERTAP_PASSCODE"))
USE_BRAZE = bool(os.getenv("BRAZE_API_KEY") and os.getenv("BRAZE_API_URL"))

def crm_update_profile(phone, opt_in=True, product_tag=None, last_interaction=None):
    if USE_CLEVERTAP:
        try:
            clevertap.upsert_profile(phone, opt_in, product_tag, last_interaction)
        except Exception as e:
            logger.error("CleverTap profile upsert failed: %s", e)

    if USE_BRAZE:
        try:
            braze.upsert_profile(phone, opt_in, product_tag, last_interaction)
        except Exception as e:
            logger.error("Braze profile upsert failed: %s", e)


def crm_track_event(phone, event_name, evt_props=None):
    if USE_CLEVERTAP:
        try:
            clevertap.send_event(phone, event_name, evt_props)
        except Exception as e:
            logger.error("CleverTap event failed: %s", e)

    if USE_BRAZE:
        try:
            braze.send_event(phone, event_name, evt_props)
        except Exception as e:
            logger.error("Braze event failed: %s", e)