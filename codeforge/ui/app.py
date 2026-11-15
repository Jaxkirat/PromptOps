"""CodeForge Gradio workspace — mounted into the FastAPI application."""

from __future__ import annotations

from typing import Any

import gradio as gr

from codeforge.ui.formatters import (
    empty_code,
    empty_tests,
    execution_markdown,
    history_choices,
    profile_html,
    quota_html,
    requirements_markdown,
    roadmap_html,
    tests_summary_markdown,
)
from codeforge.ui.handlers import (
    EXAMPLE_PROMPTS,
    current_profile,
    current_run,
    download_code,
    download_execution_report,
    download_tests,
    ensure_session,
    handle_accept_invite,
    handle_history,
    handle_load_run,
    handle_login,
    handle_logout,
    handle_new_chat,
    handle_quota,
    handle_register,
    handle_submit,
    handle_validate_invite,
    handle_refresh_approvals,
    handle_decide_approval,
    handle_feedback,
    handle_instructor_sql,
    handle_open_ticket,
    handle_refresh_tickets,
    handle_student_sql,
    instructor_sql_notice,
    is_authenticated,
    new_session,
)


def _history_dropdown(session: dict[str, Any]) -> gr.Dropdown:
    runs = handle_history(session)
    return gr.Dropdown(choices=history_choices(runs), value=None, interactive=True)


def _artifacts(run) -> tuple[str, str, str, str, str, str, str]:
    code = run.generated_code if run and run.generated_code else empty_code()
    tests = run.generated_tests if run and run.generated_tests else empty_tests()
    stdout = ((run.artifacts or {}).get("stdout") if run else "") or ""
    stderr = ((run.artifacts or {}).get("stderr") if run else "") or ""
    return (
        code,
        tests,
        tests_summary_markdown(run),
        requirements_markdown(run),
        execution_markdown(run),
        stdout,
        stderr,
    )


def _shell(session_data: dict[str, Any]):
    session_data = ensure_session(session_data)
    profile = current_profile(session_data)
    run = current_run(session_data)
    conversation = session_data.get("conversation") or []
    authed = is_authenticated(session_data)
    return (
        session_data,
        gr.update(visible=not authed),
        gr.update(visible=authed),
        conversation,
        profile_html(profile),
        quota_html(handle_quota(session_data) if authed else None),
        _history_dropdown(session_data),
        gr.update(visible=bool(profile and profile.role == "instructor")),
        gr.update(visible=len(conversation) == 0),
        *_artifacts(run),
    )


def build_interface() -> gr.Blocks:
    """Build the CodeForge Gradio Blocks application."""
    with gr.Blocks(
        title="CodeForge",
        fill_height=True,
        analytics_enabled=False,
    ) as demo:
        session = gr.State({})

        with gr.Column(visible=True, elem_classes=["auth-shell"]) as auth_view:
            gr.HTML(
                """
                <div class="brand">
                  <div class="brand-mark">CF</div>
                  <h1>CodeForge</h1>
                  <p>Describe a function in plain English. CodeForge generates
                  Python, writes pytest tests, and runs them for real.</p>
                </div>
                """
            )
            with gr.Group(elem_classes=["auth-card"]):
                with gr.Tabs() as auth_tabs:
                    with gr.Tab("Sign in", id="login"):
                        login_email = gr.Textbox(label="Email", autofocus=True)
                        login_password = gr.Textbox(label="Password", type="password")
                        login_show = gr.Checkbox(label="Show password", value=False)
                        login_btn = gr.Button("Sign in", variant="primary")
                    with gr.Tab("Create account", id="register"):
                        reg_name = gr.Textbox(label="Full name")
                        reg_email = gr.Textbox(label="Email")
                        reg_password = gr.Textbox(label="Password", type="password")
                        reg_confirm = gr.Textbox(label="Confirm password", type="password")
                        gr.Markdown(
                            "Public registration creates a **student** account. "
                            "Instructors join through an invitation link."
                        )
                        register_btn = gr.Button("Create student account", variant="primary")
                    with gr.Tab("Instructor invite", id="invite"):
                        invite_token = gr.Textbox(
                            label="Invitation token",
                            placeholder="Filled automatically from the invitation URL",
                        )
                        invite_status = gr.Markdown("")
                        invite_name = gr.Textbox(label="Full name")
                        invite_email = gr.Textbox(label="Email")
                        invite_password = gr.Textbox(label="Password", type="password")
                        invite_confirm = gr.Textbox(label="Confirm password", type="password")
                        invite_btn = gr.Button("Activate instructor account", variant="primary")
                auth_error = gr.Markdown("", elem_classes=["cf-error"])

        with gr.Column(visible=False, elem_classes=["workspace"]) as work_view:
            with gr.Row(equal_height=True):
                with gr.Column(scale=2, min_width=240, elem_classes=["sidebar"]):
                    gr.HTML(
                        '<div class="sidebar-logo"><span class="mark">CF</span> CodeForge</div>'
                    )
                    new_chat_btn = gr.Button("New chat", variant="primary")
                    history = gr.Dropdown(
                        label="Recent runs",
                        choices=[],
                        interactive=True,
                        info="Your runs only — never another user's.",
                    )
                    quota_panel = gr.HTML(quota_html(None))
                    gr.HTML(roadmap_html())
                    instructor_panel = gr.Column(visible=False)
                    with instructor_panel:
                        gr.Markdown(instructor_sql_notice())
                        ticket_list = gr.Markdown("_No assigned tickets._")
                        refresh_tickets = gr.Button("Refresh tickets", size="sm")
                        ticket_id = gr.Textbox(label="Ticket reference")
                        open_ticket = gr.Button("Open ticket", size="sm")
                        ticket_context = gr.Markdown("_Ticket context appears here._")
                        ticket_question = gr.Textbox(
                            label="Question about this ticket",
                            lines=2,
                            placeholder="Show the generated code for this ticket",
                        )
                        ticket_ask = gr.Button("Ask about this ticket", size="sm")
                        ticket_answer = gr.Markdown("")
                        approvals_view = gr.Markdown("_No pending approvals._")
                        refresh_approvals = gr.Button("Refresh approvals", size="sm")
                        approval_id = gr.Textbox(label="Approval id")
                        confirm_decision = gr.Checkbox(
                            label="I confirm this approval decision", value=False
                        )
                        with gr.Row():
                            approve_btn = gr.Button("Approve", size="sm")
                            reject_btn = gr.Button("Reject", size="sm")
                    profile_panel = gr.HTML("")
                    logout_btn = gr.Button("Log out", variant="secondary")

                with gr.Column(scale=5, elem_classes=["main-col"]):
                    empty_hero = gr.HTML(
                        """
                        <div class="empty-hero">
                          <h2>Build something with CodeForge.</h2>
                          <p>Ask for a Python function. The agents extract
                          requirements, write code, generate tests and run pytest.</p>
                        </div>
                        """
                    )
                    chatbot = gr.Chatbot(
                        label="Conversation",
                        height=420,
                        buttons=["copy"],
                        placeholder="Build something with CodeForge.",
                        elem_id="chatbot",
                    )
                    processing = gr.Markdown("")
                    with gr.Row():
                        example_buttons = [
                            gr.Button(prompt.split(" that ")[-1][:32], size="sm")
                            for prompt in EXAMPLE_PROMPTS
                        ]
                    composer = gr.Textbox(
                        label="Request",
                        placeholder="Describe the function you want…  Enter to send, Shift+Enter for a newline",
                        lines=3,
                        max_lines=8,
                        elem_id="composer",
                    )
                    send_btn = gr.Button("Send", variant="primary")

                with gr.Column(scale=4, min_width=320, elem_classes=["artifact-col"]):
                    with gr.Tabs():
                        with gr.Tab("Code"):
                            code_view = gr.Code(
                                label="Generated implementation",
                                language="python",
                                value=empty_code(),
                                interactive=False,
                                lines=18,
                                buttons=["copy"],
                            )
                            dl_code_btn = gr.DownloadButton("Download solution.py", size="sm")
                        with gr.Tab("Tests"):
                            tests_summary = gr.Markdown(tests_summary_markdown(None))
                            tests_view = gr.Code(
                                label="Generated pytest module",
                                language="python",
                                value=empty_tests(),
                                interactive=False,
                                lines=16,
                                buttons=["copy"],
                            )
                            dl_tests_btn = gr.DownloadButton("Download test_solution.py", size="sm")
                        with gr.Tab("Requirements"):
                            req_view = gr.Markdown(requirements_markdown(None))
                        with gr.Tab("Execution"):
                            exec_view = gr.Markdown(execution_markdown(None))
                            stdout_view = gr.Textbox(
                                label="pytest stdout",
                                lines=8,
                                max_lines=16,
                                interactive=False,
                            )
                            stderr_view = gr.Textbox(
                                label="pytest stderr",
                                lines=4,
                                max_lines=10,
                                interactive=False,
                            )
                            dl_exec_btn = gr.DownloadButton(
                                "Download report JSON", size="sm"
                            )
                            feedback_note = gr.Textbox(
                                label="Optional feedback",
                                lines=2,
                                placeholder="What should this result have done?",
                            )
                            with gr.Row():
                                thumb_up = gr.Button("Thumbs up", size="sm")
                                thumb_down = gr.Button("Thumbs down", size="sm")
                            feedback_status = gr.Markdown("")
                        with gr.Tab("My history"):
                            gr.Markdown(
                                "**My CodeForge History**\n\n"
                                "Questions use your signed-in account. "
                                "There is no control here to choose another user."
                            )
                            history_question = gr.Textbox(
                                label="Question",
                                lines=2,
                                placeholder="Show my last 10 prompts.",
                            )
                            history_ask = gr.Button("Ask about my history", variant="primary")
                            history_answer = gr.Markdown("_Ask a question to see your own history._")

        shell_outputs = [
            session,
            auth_view,
            work_view,
            chatbot,
            profile_panel,
            quota_panel,
            history,
            instructor_panel,
            empty_hero,
            code_view,
            tests_view,
            tests_summary,
            req_view,
            exec_view,
            stdout_view,
            stderr_view,
        ]

        def do_login(sess, email, password):
            sess, error = handle_login(sess, email, password)
            return error, *_shell(sess)

        def do_register(sess, name, email, password, confirm):
            sess, error = handle_register(sess, name, email, password, confirm)
            return error, *_shell(sess)

        def do_invite(sess, token, name, email, password, confirm):
            sess, error = handle_accept_invite(sess, token, name, email, password, confirm)
            return error, *_shell(sess)

        def do_logout(sess):
            sess = handle_logout(sess)
            return "", *_shell(sess)

        def do_new_chat(sess):
            return _shell(handle_new_chat(sess))

        def do_load(sess, run_id):
            sess, error = handle_load_run(sess, run_id)
            values = _shell(sess)
            return error, *values

        def do_send(message, sess):
            sess = ensure_session(sess)
            yield (
                "",
                message,
                sess.get("conversation") or [],
                "CodeForge is working on your request...",
                gr.update(visible=not is_authenticated(sess)),
                gr.update(visible=is_authenticated(sess)),
                *_artifacts(current_run(sess)),
                quota_html(handle_quota(sess)),
                _history_dropdown(sess),
                gr.update(visible=False),
                sess,
            )
            sess, kind, error = handle_submit(sess, message)
            note = "" if kind == "ok" else (
                f"**Daily quota exceeded.** {error}" if kind == "quota" else error
            )
            authed = is_authenticated(sess)
            conversation = sess.get("conversation") or []
            yield (
                note if kind != "session_expired" else "",
                "" if kind == "ok" else message,
                conversation,
                note,
                gr.update(visible=not authed),
                gr.update(visible=authed),
                *_artifacts(current_run(sess)),
                quota_html(handle_quota(sess)),
                _history_dropdown(sess),
                gr.update(visible=len(conversation) == 0),
                sess,
            )

        login_show.change(
            lambda show: gr.update(type="text" if show else "password"),
            inputs=login_show,
            outputs=login_password,
        )

        auth_outputs = [auth_error, *shell_outputs]
        login_btn.click(
            do_login, inputs=[session, login_email, login_password], outputs=auth_outputs
        )
        login_password.submit(
            do_login, inputs=[session, login_email, login_password], outputs=auth_outputs
        )
        register_btn.click(
            do_register,
            inputs=[session, reg_name, reg_email, reg_password, reg_confirm],
            outputs=auth_outputs,
        )
        invite_btn.click(
            do_invite,
            inputs=[
                session,
                invite_token,
                invite_name,
                invite_email,
                invite_password,
                invite_confirm,
            ],
            outputs=auth_outputs,
        )
        logout_btn.click(do_logout, inputs=[session], outputs=auth_outputs)
        new_chat_btn.click(do_new_chat, inputs=[session], outputs=shell_outputs)
        history.change(
            do_load, inputs=[session, history], outputs=[processing, *shell_outputs]
        )

        def do_refresh(sess):
            return handle_refresh_approvals(sess)

        def do_approve(sess, approval, confirmed):
            return handle_decide_approval(sess, approval, "approved", bool(confirmed))

        def do_reject(sess, approval, confirmed):
            return handle_decide_approval(sess, approval, "rejected", bool(confirmed))

        history_ask.click(
            lambda sess, question: handle_student_sql(sess, question),
            inputs=[session, history_question],
            outputs=[history_answer],
        )
        refresh_tickets.click(
            lambda sess: handle_refresh_tickets(sess),
            inputs=[session],
            outputs=[ticket_list],
        )
        open_ticket.click(
            lambda sess, chosen: handle_open_ticket(sess, chosen),
            inputs=[session, ticket_id],
            outputs=[ticket_context],
        )
        ticket_ask.click(
            lambda sess, chosen, question: handle_instructor_sql(sess, chosen, question),
            inputs=[session, ticket_id, ticket_question],
            outputs=[ticket_answer],
        )
        refresh_approvals.click(do_refresh, inputs=[session], outputs=[approvals_view])
        approve_btn.click(
            do_approve,
            inputs=[session, approval_id, confirm_decision],
            outputs=[approvals_view],
        )
        reject_btn.click(
            do_reject,
            inputs=[session, approval_id, confirm_decision],
            outputs=[approvals_view],
        )

        def do_feedback(sess, vote, note):
            return handle_feedback(sess, vote, note)

        thumb_up.click(
            lambda sess, note: do_feedback(sess, "up", note),
            inputs=[session, feedback_note],
            outputs=[feedback_status],
        )
        thumb_down.click(
            lambda sess, note: do_feedback(sess, "down", note),
            inputs=[session, feedback_note],
            outputs=[feedback_status],
        )

        send_outputs = [
            auth_error,
            composer,
            chatbot,
            processing,
            auth_view,
            work_view,
            code_view,
            tests_view,
            tests_summary,
            req_view,
            exec_view,
            stdout_view,
            stderr_view,
            quota_panel,
            history,
            empty_hero,
            session,
        ]
        send_btn.click(do_send, inputs=[composer, session], outputs=send_outputs)
        composer.submit(do_send, inputs=[composer, session], outputs=send_outputs)

        for button, prompt in zip(example_buttons, EXAMPLE_PROMPTS, strict=True):
            button.click(lambda p=prompt: p, outputs=[composer])

        dl_code_btn.click(
            lambda sess: download_code(current_run(ensure_session(sess))),
            inputs=[session],
            outputs=[dl_code_btn],
        )
        dl_tests_btn.click(
            lambda sess: download_tests(current_run(ensure_session(sess))),
            inputs=[session],
            outputs=[dl_tests_btn],
        )
        dl_exec_btn.click(
            lambda sess: download_execution_report(current_run(ensure_session(sess))),
            inputs=[session],
            outputs=[dl_exec_btn],
        )

        def on_load(request: gr.Request):
            token = ""
            try:
                token = request.query_params.get("token") or request.query_params.get("invite") or ""
            except Exception:
                token = ""
            selected = "invite" if token else "login"
            email = status = ""
            if token:
                email, status, error = handle_validate_invite(token)
                status = error or status
            return new_session(), gr.update(selected=selected), token, email, status

        demo.load(
            on_load,
            inputs=None,
            outputs=[session, auth_tabs, invite_token, invite_email, invite_status],
        )

    return demo
