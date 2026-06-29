// AccessAble India - Voice Assitive and Dictation Engine

// 1. Hover-to-Speak (Text-to-Speech Assistant)
let ttsEnabled = false;
let currentUtterance = null;

function speakText(text) {
    if (!ttsEnabled) return;
    
    // Stop any active narration
    window.speechSynthesis.cancel();
    
    if (!text || text.trim() === '') return;
    
    currentUtterance = new SpeechSynthesisUtterance(text);
    currentUtterance.rate = 1.0;
    currentUtterance.pitch = 1.0;
    
    // Attempt to set a pleasant local English or Hindi voice
    const voices = window.speechSynthesis.getVoices();
    const preferredVoice = voices.find(v => v.lang.includes('en-IN') || v.lang.includes('en-US'));
    if (preferredVoice) {
        currentUtterance.voice = preferredVoice;
    }
    
    window.speechSynthesis.speak(currentUtterance);
}

function stopSpeaking() {
    if (ttsEnabled) {
        window.speechSynthesis.cancel();
    }
}

// Set up listeners for speakable elements
document.addEventListener('DOMContentLoaded', () => {
    // Enable Hover-to-Speak on mouse movements and focus triggers
    document.body.addEventListener('mouseover', (e) => {
        const target = e.target.closest('.speakable');
        if (target && ttsEnabled) {
            // Read target text content or alt attribute for images
            const narration = target.getAttribute('aria-label') || target.getAttribute('alt') || target.innerText;
            speakText(narration);
        }
    });

    document.body.addEventListener('mouseout', (e) => {
        const target = e.target.closest('.speakable');
        if (target && ttsEnabled) {
            stopSpeaking();
        }
    });

    // Keyboard focus support (important for screen-reader/WCAG navigation)
    document.body.addEventListener('focusin', (e) => {
        const target = e.target.closest('.speakable');
        if (target && ttsEnabled) {
            const narration = target.getAttribute('aria-label') || target.getAttribute('alt') || target.innerText;
            speakText(narration);
        }
    });

    document.body.addEventListener('focusout', (e) => {
        const target = e.target.closest('.speakable');
        if (target && ttsEnabled) {
            stopSpeaking();
        }
    });
});

// Controls for TTS activation
function toggleTTS() {
    ttsEnabled = !ttsEnabled;
    const btn = document.getElementById('tts-toggle-btn');
    if (btn) {
        if (ttsEnabled) {
            btn.classList.add('active');
            btn.innerHTML = '🔊 Voice Assist: ON';
            btn.style.borderColor = 'var(--color-success)';
            speakText("Screen assistant enabled. Hover over items to hear them read aloud.");
        } else {
            btn.classList.remove('active');
            btn.innerHTML = '🔈 Voice Assist: OFF';
            btn.style.borderColor = 'var(--color-primary)';
            window.speechSynthesis.cancel();
        }
    }
}

// 2. Speech-to-Text (Voice issue reporting)
let recognition = null;
let activeTargetInputId = null;

function initSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        console.warn("Speech Recognition API is not supported in this browser.");
        return false;
    }
    
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.lang = 'en-IN'; // Indian English, very robust
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    
    recognition.onstart = () => {
        console.log("Voice recording active...");
        const micBtn = document.getElementById('voice-trigger-btn');
        if (micBtn) micBtn.classList.add('listening');
    };
    
    recognition.onspeechend = () => {
        recognition.stop();
    };
    
    recognition.onend = () => {
        const micBtn = document.getElementById('voice-trigger-btn');
        if (micBtn) micBtn.classList.remove('listening');
    };
    
    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        console.log("Voice result: ", transcript);
        
        if (activeTargetInputId) {
            const targetField = document.getElementById(activeTargetInputId);
            if (targetField) {
                if (targetField.value) {
                    targetField.value += " " + transcript;
                } else {
                    targetField.value = transcript;
                }
                // Trigger event change
                targetField.dispatchEvent(new Event('input'));
            }
        }
    };
    
    recognition.onerror = (event) => {
        console.error("Speech recognition error: ", event.error);
        alert("Speech Recognition Error: " + event.error);
    };
    
    return true;
}

function startVoiceDictation(targetInputId) {
    activeTargetInputId = targetInputId;
    if (!recognition) {
        const initialized = initSpeechRecognition();
        if (!initialized) {
            alert("Your browser does not support voice dictation. Please type instead.");
            return;
        }
    }
    try {
        recognition.start();
    } catch (e) {
        console.log("Voice recognition already running.");
    }
}
