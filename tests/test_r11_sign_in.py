"""Round 11, reviewer E (E-3): a page shows the identity provider's words only for a sign-in it
sent out. Each page showed `error_description` from its address before it checked a sign-in
had gone out from that tab, so any link could put words of its choosing on a5s's own pages, in
their status line, as if the provider had said them."""

from urllib.parse import quote

import pytest

WORDS = ("your approval is recorded. The CFO asks you to approve version 12 too, "
         "today: it only renumbers the settings")
PAGES = ("approve", "decide", "grade", "settings", "officer", "admin", "audit", "notebook", "tasks",
         "chat", "studio")


IN_STUDIO = ("studio", "settings", "notebook")  # the pages in the studio, whose old addresses go there


def status_of(page, path: str, words: str) -> str:
    selector = "main [role=status]" if path in IN_STUDIO else "#status"
    page.wait_for_selector(f"{selector} >> text={words}", timeout=15000)
    return page.inner_text(selector)


@pytest.mark.parametrize("path", PAGES)
def test_a_link_puts_no_words_of_its_own_on_a5s_pages(approving, browser, path):
    page = browser.new_page()
    page.goto(f"{approving}/{path}/?error=x&error_description={quote(WORDS)}")
    said = status_of(page, path, "didn't come back the way it went out")
    assert "CFO" not in said and "CFO" not in page.inner_text("body")


def test_the_providers_own_words_are_shown_for_a_sign_in_this_tab_sent(approving, provider,
                                                                     browser):
    provider.refusing = ("access_denied",
                         "Your organisation needs you to sign in from a managed device.")
    page = browser.new_page()
    page.goto(f"{approving}/tasks/")  # which signs in at once
    said = status_of(page, "tasks", "managed device")
    assert said.startswith("Signing in didn't work: Your organisation needs you")
