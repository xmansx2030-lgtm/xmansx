from celery import shared_task
from django.conf import settings

from academics.services.ministry_calendar import apply_ministry_calendars, sync_ministry_calendar


@shared_task(name="academics.sync_ministry_calendar", ignore_result=True)
def sync_official_calendar():
    if not settings.MINISTRY_CALENDAR_ENABLED:
        return {"status": "DISABLED"}
    result = sync_ministry_calendar()
    if result["status"] == "FETCHED":
        apply_ministry_calendars()
    return result


@shared_task(name="academics.apply_ministry_calendars", ignore_result=True)
def activate_official_calendars():
    return apply_ministry_calendars()
