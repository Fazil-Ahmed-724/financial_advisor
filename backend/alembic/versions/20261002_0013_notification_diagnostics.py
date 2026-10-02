"""Allow explicit diagnostic test notification events.

Revision ID: 20261002_0013
Revises: 20261002_0012
"""
from alembic import op

revision="20261002_0013";down_revision="20261002_0012";branch_labels=None;depends_on=None

def upgrade():
    op.drop_constraint("ck_notification_event_type","notification_events",type_="check")
    op.create_check_constraint("ck_notification_event_type","notification_events","event_type IN ('reminder_due','assistant_response_ready','feedback_review_status_changed','test_notification')")

def downgrade():
    op.execute("DELETE FROM notification_deliveries WHERE event_id IN (SELECT id FROM notification_events WHERE event_type='test_notification')")
    op.execute("DELETE FROM notification_events WHERE event_type='test_notification'")
    op.drop_constraint("ck_notification_event_type","notification_events",type_="check")
    op.create_check_constraint("ck_notification_event_type","notification_events","event_type IN ('reminder_due','assistant_response_ready','feedback_review_status_changed')")
