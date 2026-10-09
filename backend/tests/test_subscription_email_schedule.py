from beat_schedule import build_beat_schedule


def test_enabling_subscription_mail_keeps_existing_operational_schedule():
    options = {"heartbeat_interval_seconds": 120, "backup_enabled": True,
               "backup_interval_seconds": 86400, "ministry_calendar_enabled": True}
    previous = build_beat_schedule(**options)
    enabled = build_beat_schedule(**options, subscription_email_enabled=True)
    assert {key: enabled[key] for key in previous} == previous
    assert enabled["subscription-manager-emails"]["task"] == "subscriptions.process_manager_emails"
    assert "subscription-manager-emails" not in previous
