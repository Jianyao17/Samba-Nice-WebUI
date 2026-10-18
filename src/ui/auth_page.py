from nicegui import app, ui

from src.core.security import verify_credentials


def create_auth_page():
    ui.page_title("Login - Samba-Nice-WebUI")
    ui.colors(primary="#2563eb", secondary="#64748b", accent="#0ea5e9", positive="#10b981", negative="#ef4444")

    with ui.column().classes("w-full h-screen items-center justify-center bg-slate-100 dark:bg-slate-900 p-4"):
        with ui.card().classes("w-full max-w-md p-8 shadow-xl rounded-xl border border-slate-200 dark:border-slate-800"):
            # 1. Header with branding
            with ui.row().classes("items-center justify-center gap-3 w-full mb-6"):
                ui.icon("folder_shared", size="2.5rem").classes("text-blue-600")
                ui.label("Samba-Nice-WebUI").classes("text-2xl font-bold text-slate-800 dark:text-slate-100")

            ui.label("Sign in to manage Samba shares").classes("text-sm text-slate-500 mb-6 text-center w-full")

            # 2. Form fields
            username_input = ui.input("Username").props("outlined dense").classes("w-full mb-4")
            password_input = ui.input("Password", password=True, password_toggle_button=True).props("outlined dense").classes("w-full mb-6")

            # 3. Authentication handler
            def try_login():
                username = username_input.value or ""
                password = password_input.value or ""

                if verify_credentials(username, password):
                    # Set session state and navigate to dashboard
                    app.storage.user["authenticated"] = True
                    ui.notify("Login successful!", type="positive")
                    ui.navigate.to("/")
                else:
                    ui.notify("Invalid username or password.", type="negative")

            # 4. Submit button and enter key triggers
            password_input.on("keydown.enter", try_login)
            username_input.on("keydown.enter", try_login)

            ui.button("Sign In", on_click=try_login, icon="login").props("unelevated").classes("w-full py-2 bg-blue-600 text-white font-medium rounded-lg")
