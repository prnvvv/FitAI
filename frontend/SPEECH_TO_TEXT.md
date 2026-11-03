# Speech input (dictation)

FitAI dictation uses the browser's **Web Speech API** (`SpeechRecognition` /
`webkitSpeechRecognition`). Recognition happens in the browser; the recognised **text** is placed in
the chat composer, where the user reviews and edits it before sending. Nothing is sent
automatically.

The previous IBM Granite backend transcription (model download, `/api/v1/stt/*` routes, the
`fitai-stt` Render service) has been removed. No FitAI backend setting, service or credential is
involved in dictation.

## Architecture

| Piece | File |
|---|---|
| API detection, language list, error messages | `frontend/src/services/speechRecognition.ts` |
| Lifecycle hook (start, stop, cancel, cleanup) | `frontend/src/hooks/useSpeechRecognition.ts` |
| Microphone, language picker and status UI | `frontend/src/components/chat/Composer.tsx` |
| Test double for the browser API | `frontend/src/test/fakeSpeechRecognition.ts` |

Behaviour:

* The microphone permission prompt appears only after the user clicks the microphone button.
* Only one recognition session exists at a time; repeated clicks are ignored.
* Interim words are shown in the status line while speaking. Only **finalised** phrases are
  inserted, at the caret (or replacing the selection), so typed text is never overwritten. Each
  finalised result is delivered once, even if the browser re-sends it.
* Stop keeps whatever was heard; Cancel (button or Esc) discards the session.
* Sending is disabled while dictating, so words that are not final yet cannot be lost.
* Switching conversation, unmounting, or hiding the tab stops listening and releases the microphone.
  A session also ends on its own after 60 seconds.
* States: idle, requesting permission, listening, finalizing, completed, error, unsupported.

## Languages

The picker offers English (India) `en-IN` (default unless the browser language is another listed
one), English (US) `en-US`, Tamil `ta-IN` and Hindi `hi-IN`. Browsers do not publish which languages
their recognition service supports, so FitAI does not claim any language works: if the selected
language is unavailable the browser raises `language-not-supported` and the composer says so. The
choice is remembered in `localStorage`.

## Browser support and privacy

* **Chrome and Edge (desktop and Android)** implement the API. Safari support is partial and
  version-dependent, and **Firefox does not support `SpeechRecognition`**. Unsupported browsers see a
  disabled microphone with an explanation, and typing is unaffected.
* **Remote processing.** In Chromium browsers the audio is sent to a browser-managed speech service
  (Google for Chrome, Microsoft for Edge). Recognition therefore needs a network connection, is not
  guaranteed to work offline, and is governed by the browser vendor's privacy policy.
* **FitAI never receives, stores or uploads the audio.** There is no recording code and no
  transcription endpoint.
* **HTTPS.** Microphone access requires a secure context. Deployed sites must use HTTPS (Vercel
  does by default); `http://localhost` is the development exception. On an insecure origin the
  microphone is disabled with an explanation.

## Manual verification checklist (real browsers)

Automated tests mock the browser API, so they do **not** prove real microphone behaviour. Run this
in **Chrome** and **Edge** (desktop), on `http://localhost:5173` and on the deployed HTTPS site, with a
working microphone and an internet connection:

1. Open the chat. The microphone button and language picker are visible; no permission prompt yet.
2. Click the microphone. The browser asks for permission. Allow it. The status line reads
   "Listening… speak now" and the red dot pulses.
3. Say a sentence. Interim words appear in the status line; after a pause the finalised text appears
   in the message box. The message is **not** sent.
4. Type "Hello" first, put the caret in the middle, dictate again: the text is inserted at the caret
   and the existing text is intact.
5. Click Stop: the status reads "Added to your message. Review and edit it before sending." Edit the
   text and press Enter: the edited text is sent through the normal chat flow.
6. Dictate, then press Esc (or Cancel): nothing is inserted and the microphone indicator in the
   browser tab disappears.
7. Pick Hindi or Tamil and dictate in that language; confirm the text, or that a clear
   "language not supported" message appears.
8. Block the microphone for the site (address-bar lock icon), click the microphone: a message
   explains how to re-enable it. Re-allow and confirm it works. Dismiss the prompt without choosing:
   the same guidance appears.
9. Unplug/disable the microphone and try: a "no microphone found" message appears.
10. Go offline (DevTools -> Network -> Offline) and try: a network error message appears and the
    composer keeps working for typing.
11. Start dictating and switch to another tab: listening stops and the tab's recording indicator
    goes away. Switch conversations mid-dictation: no text lands in the new conversation.
12. Click the microphone rapidly several times: only one session starts.
13. Open the site in Firefox: the microphone is disabled with the "not supported" explanation and
    typing still works.
14. Confirm in DevTools -> Network that no audio or `/stt` request is made.

Known limitation to watch for in step 3: some Android Chrome versions re-emit earlier results in
continuous mode. FitAI de-duplicates by result index, but report any repeated words you see.
