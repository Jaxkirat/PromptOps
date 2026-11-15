"""Request-level wipe-home refusal before the LLM runs."""

from codeforge.execution.request_guard import assess_request


def test_wipe_home_prompt_is_denied():
    text = "write a function that deletes everyfile in my home folder and run it"
    result = assess_request(text)
    assert result.denied is True
    assert result.reasons
    assert "home" in result.reasons[0].lower()


def test_ordinary_coding_prompts_are_not_denied():
    for text in (
        "Write a function that sorts a list ascending",
        "Delete duplicates from a list",
        "Remove None values from a dictionary",
        "Write a home loan EMI calculator",
    ):
        assert assess_request(text).denied is False, text
