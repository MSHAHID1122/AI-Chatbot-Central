import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# In-memory store for demo
crm_data = {"users": {}, "events": []}


def crm_track_event(user_id: str, event_type: str, metadata: dict = None):
    try:
        event = {
            "user_id": user_id,
            "event_type": event_type,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }
        crm_data["events"].append(event)

        if user_id not in crm_data["users"]:
            crm_data["users"][user_id] = {
                "first_seen": datetime.now().isoformat(),
                "last_activity": datetime.now().isoformat(),
                "opt_in": False,
                "channels": [],
            }

        user = crm_data["users"][user_id]
        user["last_activity"] = datetime.now().isoformat()

        # Track channel usage
        channel = (metadata or {}).get("channel")
        if channel and channel not in user["channels"]:
            user["channels"].append(channel)

        logger.info(f"CRM event tracked: {event_type} for {user_id}")
        return True
    except Exception as e:
        logger.error(f"CRM tracking error: {e}")
        return False


def crm_update_profile(user_id: str, profile_data: dict):
    try:
        if user_id not in crm_data["users"]:
            crm_data["users"][user_id] = {
                "first_seen": datetime.now().isoformat(),
                "last_activity": datetime.now().isoformat(),
                "opt_in": False,
                "channels": [],
            }

        user = crm_data["users"][user_id]

        if "opt_in" in profile_data:
            user["opt_in"] = bool(profile_data["opt_in"])

        if "channel" in profile_data:
            if profile_data["channel"] not in user["channels"]:
                user["channels"].append(profile_data["channel"])

        for k, v in profile_data.items():
            if k not in ["opt_in", "channel"]:
                user[k] = v

        logger.info(f"CRM profile updated: {user_id}")
        return True
    except Exception as e:
        logger.error(f"CRM profile update error: {e}")
        return False