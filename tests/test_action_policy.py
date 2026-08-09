from modules.action_policy import classify_text, resolve


def test_git_policy_is_central_and_operation_specific():
    assert resolve("git_operation", {"operation": "status"}, base_risk="medium").requires_confirmation is False
    assert resolve("git_operation", {"operation": "push"}, base_risk="medium").risk == "high"
    assert resolve("git_operation", {"operation": "pull"}, base_risk="medium").can_auto_approve is True


def test_external_action_is_high_and_never_auto_approved():
    policy = resolve("send_whatsapp_message", base_risk="high", base_confirmation=True)
    assert policy.external is True
    assert policy.requires_confirmation is True
    assert policy.can_auto_approve is False


def test_attendees_make_calendar_action_external():
    policy = resolve(
        "create_calendar_event",
        {"attendees": ["person@example.invalid"]},
        base_risk="high",
        base_confirmation=True,
    )
    assert policy.external is True


def test_calendar_mutation_is_external_even_without_attendees():
    policy = resolve("update_calendar_event", base_risk="medium", base_confirmation=True)
    assert policy.external is True
    assert policy.risk == "high"
    assert policy.can_auto_approve is False


def test_direct_text_classification_is_conservative():
    assert classify_text("manda mensagem para alguém").external is True
    assert classify_text("git push").risk == "high"
    assert classify_text("abre o spotify").requires_confirmation is False
