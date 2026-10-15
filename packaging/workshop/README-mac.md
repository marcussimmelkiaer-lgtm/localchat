# LocalChat for Mac

A ChatGPT-style chat app that runs an AI model **entirely on your own Mac**.
No cloud, no account, nothing you type leaves the machine.
It's built on [NobodyWho](https://github.com/nobodywho-ooo/nobodywho).

You need a Mac with **Apple Silicon** (M1 or newer). To check, open
 → About This Mac: the "Chip" line should say Apple M1, M2, M3 or similar.

## Install (once)

1. Open **Terminal**: press ⌘-Space, type `Terminal` and press Return.
2. Paste this line, then press Return:

   ```
   git clone REPO_URL ~/LocalChat
   ```

   If your Mac asks to install the "command line developer tools", click
   **Install**, wait for it to finish, then paste the line again.
3. In Finder, open your home folder → **LocalChat**, and double-click
   **Start LocalChat.command**.

The first start takes a few minutes. It downloads Python, the app's components
and a small AI model (about 640 MB) into the LocalChat folder, and you can watch
the progress in the Terminal window. When the LocalChat window opens, you can
close Terminal.

## Every time after that

Double-click **Start LocalChat.command**. It works without internet.

## Bigger, smarter models

The default model is small so it downloads quickly. For better answers,
especially when analysing uploaded spreadsheets or PDFs, click **Models** at the
bottom of the sidebar and download **Qwen3 4B**.

## Experiment: change how the model behaves

Everything you can tweak is in **`config.toml`** in the LocalChat folder (it's
created on the first start). Open it in any text editor, change a value, save,
and restart LocalChat. Each setting is explained in the file:

- **System prompt**: the model's standing instructions (its role, tone, rules).
- **Temperature**: how predictable or creative the answers are.
- **Thinking**: let the model reason step by step before it answers.
- **File uploads**: show or hide the paperclip button for attaching files.
- **Tools**: let the model call Python functions to get the time, the weather,
  a Wikipedia article, exact numbers from a spreadsheet in the `data` folder,
  or passages from your own documents in the `rag` folder.
  They're all off at first, so ask a question, switch the tool on, and ask
  again. The tools themselves are in `backend/tools.py`, which also shows how
  to write your own.

## If something goes wrong

- **"Setup did not finish"**: check the internet connection and double-click
  **Start LocalChat.command** again. It picks up where it left off.
- **The app window doesn't appear**: the file `LocalChat.log` in the LocalChat
  folder says why.
- **Uninstall**: delete the LocalChat folder. Downloaded models are kept in
  `~/Library/Application Support/nobodywho` and can be deleted too.
