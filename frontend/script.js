// @ts-nocheck
(function () {
  'use strict';

  var API_BASE = "http://127.0.0.1:8000";

  // Elements
  var recordBtn    = document.getElementById("recordBtn");
  var statusEl     = document.getElementById("status");
  var statusText   = document.getElementById("statusText");
  var conversation = document.getElementById("conversation");
  var sessionIdEl  = document.getElementById("sessionId");
  var historyBtn   = document.getElementById("historyBtn");
  var player       = document.getElementById("player");

  // Session id in URL (?session_id=...)
  var sessionId = (function () {
    var u = new URL(window.location.href);
    var sid = u.searchParams.get("session_id");
    if (!sid) {
      sid = (crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
      u.searchParams.set("session_id", sid);
      window.history.replaceState({}, "", u.toString());
    }
    if (sessionIdEl) sessionIdEl.textContent = sid;
    return sid;
  })();

  // History button -> open backend JSON for this session
  if (historyBtn) {
    historyBtn.addEventListener("click", function () {
      var url = API_BASE + "/agent/history/" + encodeURIComponent(sessionId);
      window.open(url, "_blank");
    });
  }

  // Helpers
  function setStatus(kind, label) {
    statusEl.className = "status-pill " + kind;
    statusText.textContent = label;
  }

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, function (m) {
      return (
        m === "&" ? "&amp;" :
        m === "<" ? "&lt;"  :
        m === ">" ? "&gt;"  :
        m === '"' ? "&quot;":
                    "&#039;"
      );
    });
  }

  function addMessage(role, text) {
    var row = document.createElement("div");
    row.className = "msg " + role;

    var bubble = document.createElement("div");
    bubble.className = "bubble";
    var who = (role === "user") ? "You" : "AI";
    bubble.innerHTML = '<span class="label">' + who + ':</span>' + escapeHtml(text);

    row.appendChild(bubble);
    conversation.appendChild(row);
    conversation.scrollTop = conversation.scrollHeight;
  }

  // Recording state
  var mediaRecorder = null;
  var chunks = [];
  var isRecording = false;

  if (recordBtn) {
    recordBtn.addEventListener("click", function () {
      if (!isRecording) {
        // START recording
        navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
          mediaRecorder = new MediaRecorder(stream);
          chunks = [];

          mediaRecorder.ondataavailable = function (e) {
            if (e.data && e.data.size > 0) chunks.push(e.data);
          };

          mediaRecorder.onstart = function () {
            isRecording = true;
            recordBtn.classList.add("recording");
            var t = recordBtn.querySelector(".btn-text");
            if (t) t.textContent = "Stop Recording";
            setStatus("status-rec", "Recording…");
          };

          mediaRecorder.onstop = function () {
            // Upload & process
            setStatus("status-thinking", "Thinking…");
            try {
              var blob = new Blob(chunks, { type: "audio/webm" });
              if (!blob.size) {
                setStatus("status-error", "No audio captured");
                resetButton();
                return;
              }

              var file = new File([blob], "mic_" + Date.now() + ".webm", { type: "audio/webm" });
              var form = new FormData();
              form.append("file", file);
              // Optional: voice override
              // form.append("voiceId", "en-UK-hazel");

              fetch(API_BASE + "/agent/chat/" + encodeURIComponent(sessionId), {
                method: "POST",
                body: form
              })
              .then(function (resp) {
                if (!resp.ok) {
                  return resp.json().then(function (j) {
                    var detail = j && j.detail ? j.detail : ("HTTP " + resp.status);
                    throw new Error(detail);
                  }).catch(function () {
                    throw new Error("HTTP " + resp.status);
                  });
                }
                return resp.json();
              })
              .then(function (data) {
                if (data.transcript) addMessage("user", data.transcript);
                if (data.llm_text)   addMessage("ai",   data.llm_text);

                var url = (data.audio_url && data.audio_url.indexOf("http") === 0)
                  ? data.audio_url
                  : API_BASE + (data.audio_url || "");

                player.src = url;
                player.onended = function () { setStatus("status-done", "Completed!"); };
                player.play().catch(function () { /* autoplay might be blocked */ });

                setStatus("status-done", "Completed!");
              })
              .catch(function (err) {
                console.error(err);
                setStatus("status-error", "Failed: " + err.message);
                addMessage("ai", "Sorry, I’m having trouble connecting right now.");
              })
              .finally(function () {
                resetButton();
              });

            } catch (err) {
              console.error(err);
              setStatus("status-error", "Failed: " + err.message);
              addMessage("ai", "Sorry, I’m having trouble connecting right now.");
              resetButton();
            }
          };

          mediaRecorder.start();
        })
        .catch(function (err) {
          console.error(err);
          setStatus("status-error", "Mic permission blocked");
        });

      } else {
        // STOP recording
        if (mediaRecorder && mediaRecorder.state === "recording") {
          mediaRecorder.stop();
        }
      }
    });
  }

  function resetButton() {
    recordBtn.classList.remove("recording");
    var t = recordBtn.querySelector(".btn-text");
    if (t) t.textContent = "Start Recording";
    isRecording = false;
  }

  // Initial state
  setStatus("status-idle", "Idle");
})();