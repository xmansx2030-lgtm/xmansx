from academics.ministry_models import CalendarProfile, SchoolCalendarPolicy


def can_prepare_ministry_year(year):
    return (
        year.status == "UPCOMING"
        and year.ministry_snapshot_id is not None
        and SchoolCalendarPolicy.objects.filter(
            school_id=year.school_id, profile=CalendarProfile.NATIONAL
        ).exists()
    )
