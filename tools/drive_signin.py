#!/usr/bin/env python3
"""Drive the local open-source Chromium (Playwright build) through the
Google sign-in flow for the Location Sharing connector.

Step-driven: each invocation performs ONE named step against the
persistent profile and screenshots the result, so a human can supply
whatever only a human can supply (2SV approval, etc.) between steps.

Steps:
  open        launch profile, go to google.com/maps, screenshot
  email       type the account email and click Next, screenshot
  state       screenshot + dump visible text of the current page
  cookies     export storage_state cookies to a Netscape cookies.txt
              (only google.com cookies), print names/counts only

The browser runs headed under Xvfb (xvfb-run) to look like a normal
browser. Profile lives beside this script in ./profile (mode 700).
No password is ever handled by this script.
"""
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, "profile")
SHOTS = os.path.join(HERE, "shots")
STATE_FILE = os.path.join(HERE, "storage_state.json")
os.makedirs(SHOTS, exist_ok=True)
os.chmod(PROFILE, 0o700) if os.path.exists(PROFILE) else None

ACCOUNT_EMAIL = os.environ.get("GLS_ACCOUNT", "")


def proxy_config():
    """Route through the local CONNECT forwarder (local_proxy.py).

    The VM egress proxy TLS-intercepts with a local egress-proxy CA,
    which system tools trust via /etc/ssl/certs but this Chromium build
    does not (it ships the Chrome Root Store only, and it could not
    resolve the proxy hostname either). The forwarder on 127.0.0.1:18080
    makes the upstream connection with the system resolver. The context
    sets ignore_https_errors for this dedicated profile only, which
    accepts that CA's certs, the same trust every other tool on
    this VM already extends to that proxy.
    """
    return {"server": os.environ.get("GLS_PROXY", "http://127.0.0.1:18080")}


def shot(page, name):
    path = os.path.join(SHOTS, name + ".png")
    page.screenshot(path=path)
    return path


def visible_text(page):
    try:
        return page.inner_text("body")[:2000]
    except Exception as exc:
        return f"<no body text: {exc.__class__.__name__}>"


def harden_profile():
    """Turn off Chromium's password saving for this profile.

    A password typed here is used for this sign-in only. It must never
    be saved by the browser, and this script never writes it anywhere.
    """
    prefs_path = os.path.join(PROFILE, "Default", "Preferences")
    if not os.path.exists(prefs_path):
        return
    try:
        with open(prefs_path) as fh:
            prefs = json.load(fh)
        prefs.setdefault("credentials_enable_service", False)
        prefs.setdefault("autofill", {})["enabled"] = False
        prefs.setdefault("profile", {})["password_manager_enabled"] = False
        with open(prefs_path, "w") as fh:
            json.dump(prefs, fh)
    except Exception:
        pass


def fill_email_and_next(page):
    if "accounts.google.com" not in page.url:
        page.goto("https://accounts.google.com/ServiceLogin?continue=https://www.google.com/maps",
                  timeout=90000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
    field = None
    for selector in ("#identifierId", 'input[name="identifier"]',
                     'input[type="email"]', 'input[autocomplete="username"]'):
        loc = page.locator(selector)
        try:
            loc.wait_for(state="visible", timeout=8000)
            field = loc
            break
        except Exception:
            continue
    if field is None:
        raise RuntimeError("email field never became visible")
    current = ""
    try:
        current = field.input_value()
    except Exception:
        pass
    if ACCOUNT_EMAIL not in current:
        field.click()
        field.press_sequentially(ACCOUNT_EMAIL, delay=40)
    page.wait_for_timeout(500)
    page.click("#identifierNext", timeout=10000)
    page.wait_for_timeout(6000)


def export_cookies(ctx):
    cookies = ctx.cookies()
    google = [c for c in cookies if "google." in c.get("domain", "")]
    out_path = os.path.join(HERE, "cookies.txt")
    lines = ["# Netscape HTTP Cookie File",
             "# Exported by gls-browser driver from its own local profile. Values stay in this file only."]
    for c in google:
        domain = c["domain"]
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        secure = "TRUE" if c.get("secure") else "FALSE"
        expiry = int(c.get("expires", 0)) if c.get("expires", 0) > 0 else 0
        lines.append("\t".join([domain, flag, c.get("path", "/"), secure,
                                str(expiry), c["name"], c["value"]]))
    with open(out_path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    os.chmod(out_path, 0o600)
    print(json.dumps({
        "exported": len(google),
        "names": sorted({c["name"] for c in google}),
        "path": out_path,
    }, indent=2), flush=True)
    return google


def main():
    step = sys.argv[1] if len(sys.argv) > 1 else "state"
    harden_profile()
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            PROFILE,
            executable_path=os.environ.get("GLS_CHROMIUM_EXE") or None,
            proxy=proxy_config(),
            ignore_https_errors=True,
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1280,900",
            ],
            viewport={"width": 1280, "height": 900},
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/159.0.0.0 Safari/537.36"),
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        step_error = None
        try:
            if step == "open":
                page.goto("https://www.google.com/maps?hl=en", timeout=90000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
            elif step == "email":
                fill_email_and_next(page)
            elif step == "full":
                # One-session sign-in: email, then a password read from
                # stdin (never stored, never logged), then wait out the
                # verification step, which the account owner completes
                # on their own phone. Ends by exporting cookies.
                fill_email_and_next(page)
                # Google's identifier->challenge transition can stall on
                # its top progress bar for a long time through the proxy
                # (seen 2026-10-29: URL already challenge/pwd, page still
                # showing the identifier form with a stuck loading bar).
                # Poll up to 150s; re-click Next once if the identifier
                # form is still up after 60s.
                pw_field = None
                wait_deadline = time.time() + 150
                next_reclicked = False
                reloaded = False
                while time.time() < wait_deadline and pw_field is None:
                    for selector in ('input[type="password"]', 'input[name="Passwd"]'):
                        loc = page.locator(selector)
                        try:
                            if loc.first.is_visible(timeout=800):
                                pw_field = loc.first
                                break
                        except Exception:
                            continue
                    if pw_field is not None:
                        break
                    if not next_reclicked and time.time() > wait_deadline - 90:
                        next_reclicked = True
                        try:
                            page.click("#identifierNext", timeout=3000)
                            print("TRANSITION: re-clicked identifier Next", flush=True)
                        except Exception:
                            pass
                    if not reloaded and time.time() > wait_deadline - 50 \
                            and "challenge/pwd" in page.url:
                        reloaded = True
                        try:
                            page.reload(timeout=60000, wait_until="domcontentloaded")
                            print("TRANSITION: reloaded stalled challenge page", flush=True)
                        except Exception:
                            pass
                    page.wait_for_timeout(2000)
                if pw_field is None:
                    shot(page, f"full-nopw-{int(time.time())}")
                    raise RuntimeError("password field never appeared, page text: "
                                       + visible_text(page)[:400])
                print("READY_FOR_PASSWORD", flush=True)
                password = sys.stdin.readline()
                if not password or not password.strip():
                    raise RuntimeError("no password received on stdin")
                password = password.rstrip("\n")
                pw_field.click()
                pw_field.press_sequentially(password, delay=30)
                password = None
                page.wait_for_timeout(500)
                page.click("#passwordNext", timeout=10000)
                print("PASSWORD_SUBMITTED", flush=True)
                deadline = time.time() + 360
                last_url = ""
                while time.time() < deadline:
                    page.wait_for_timeout(5000)
                    url = page.url
                    if url != last_url:
                        last_url = url
                        print("NOW_AT:", url[:160], flush=True)
                        shot(page, f"full-wait-{int(time.time())}")
                        print("PAGE_TEXT:", visible_text(page)[:600].replace("\n", " | "), flush=True)
                    if "google.com/maps" in url or "myaccount.google.com" in url:
                        break
                    if "/signin/rejected" in url:
                        raise RuntimeError("Google rejected this sign-in (signin/rejected)")
                if "google.com/maps" not in page.url:
                    page.goto("https://www.google.com/maps?hl=en", timeout=90000,
                              wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)
                print("FINAL_URL:", page.url, flush=True)
                export_cookies(ctx)
            elif step == "probe":
                page.goto("https://accounts.google.com/ServiceLogin?continue=https://www.google.com/maps",
                          timeout=90000, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                shot(page, f"probe-1-{int(time.time())}")
                print("PROBE1_URL:", page.url)
                print("PROBE1_TEXT:", visible_text(page)[:900].replace("\n", " | "))
                try:
                    page.get_by_text("Try another way", exact=False).first.click(timeout=6000)
                    page.wait_for_timeout(5000)
                    shot(page, f"probe-2-{int(time.time())}")
                    print("PROBE2_URL:", page.url)
                    print("PROBE2_TEXT:", visible_text(page)[:1500].replace("\n", " | "))
                except Exception as exc:
                    print("PROBE2: no Try-another-way click:", exc.__class__.__name__)
            elif step == "cookies":
                export_cookies(ctx)
        except Exception as exc:  # report the page state, never die silently
            step_error = f"{exc.__class__.__name__}: {str(exc)[:300]}"
        # common reporting
        try:
            path = shot(page, f"step-{step}-{int(time.time())}")
        except Exception:
            path = "<screenshot failed>"
        print("STEP_ERROR:", step_error)
        print("URL:", page.url)
        try:
            print("TITLE:", page.title())
        except Exception:
            print("TITLE: <unknown>")
        print("SCREENSHOT:", path)
        print("TEXT:", visible_text(page)[:1200].replace("\n", " | "))
        ctx.close()


if __name__ == "__main__":
    main()
