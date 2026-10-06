# LocalChat for Windows

A ChatGPT-style chat app that runs an AI model **entirely on your own PC**.
No cloud, no account, nothing you type leaves the machine.
It's built on [NobodyWho](https://github.com/nobodywho-ooo/nobodywho).

You need Windows 10 or 11 (64-bit).

## Install (once)

1. If you don't have Git yet, install it from
   [git-scm.com/download/win](https://git-scm.com/download/win). The default
   options are fine.
2. Open **PowerShell**: press the Windows key, type `PowerShell` and press Enter.
3. Paste this line, then press Enter:

   ```
   git clone REPO_URL $HOME\LocalChat
   ```

4. In File Explorer, open your user folder → **LocalChat**, and double-click
   **Start LocalChat.bat**.

The first start takes a few minutes. It downloads Python, the app's components
and a small AI model (about 640 MB) into the LocalChat folder, and you can watch
the progress in the black window. That window closes by itself when LocalChat
opens.

## Every time after that

Double-click **Start LocalChat.bat**. It works without internet.

## Bigger, smarter models

The default model is small so it downloads quickly. For better answers,
especially when analysing uploaded spreadsheets or PDFs, click **Models** at the
bottom of the sidebar and download **Qwen3 4B**.

## If something goes wrong

- **"Setup did not finish"**: check the internet connection and double-click
  **Start LocalChat.bat** again. It picks up where it left off.
- **The app window doesn't appear**: the file `LocalChat.log` in the LocalChat
  folder says why.
- **Uninstall**: delete the LocalChat folder. Downloaded models are kept in
  `%LOCALAPPDATA%\nobodywho` and can be deleted too.
