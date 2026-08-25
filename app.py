import streamlit as st
import streamlit.components.v1 as components
from youtube_transcript_api import YouTubeTranscriptApi
import PyPDF2
from google import genai
import re
import json
import math
import time

# ==========================================
# NOTEBOOKLM DESIGN STYLING (CSS)
# ==========================================

def apply_notebooklm_css():
    st.markdown("""
    <style>
    .stApp {
        background-color: #f0f4f9;
        font-family: 'Google Sans', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        color: #1f1f1f;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #ffffff;
        border: 1px solid #e1e3e1;
        border-radius: 20px;
        padding: 24px;
        box-shadow: 0 1px 3px rgba(60, 64, 67, 0.08), 0 4px 8px rgba(60, 64, 67, 0.04);
        margin-bottom: 20px;
    }
    .category-badge {
        background-color: #e8f0fe;
        color: #0b57d0;
        font-size: 11px;
        font-weight: 700;
        padding: 5px 12px;
        border-radius: 16px;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        display: inline-block;
        margin-bottom: 14px;
    }
    .correct-box {
        background-color: #e6f4ea;
        border: 1px solid #ceead6;
        border-left: 5px solid #137333;
        padding: 14px 18px;
        border-radius: 12px;
        margin-top: 14px;
        color: #137333;
        font-weight: 500;
        font-size: 14px;
    }
    .incorrect-box {
        background-color: #fce8e6;
        border: 1px solid #fad2cf;
        border-left: 5px solid #c5221f;
        padding: 14px 18px;
        border-radius: 12px;
        margin-top: 14px;
        color: #c5221f;
        font-weight: 500;
        font-size: 14px;
    }
    .explanation-box {
        background-color: #f8f9fa;
        border: 1px solid #e8eaed;
        border-left: 5px solid #1a73e8;
        padding: 14px 18px;
        border-radius: 12px;
        margin-top: 12px;
        font-size: 14px;
        color: #3c4043;
        line-height: 1.6;
    }
    div.stButton > button[kind="primary"] {
        border-radius: 24px;
        background-color: #0b57d0;
        font-weight: 600;
        border: none;
        padding: 10px 24px;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #0842a0;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def extract_youtube_id(url):
    regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(regex, url)
    return match.group(1) if match else None

def get_youtube_transcript(video_id):
    try:
        api = YouTubeTranscriptApi()
        fetched = None
        for lang in [['hi', 'en', 'en-IN'], ['en']]:
            try:
                fetched = api.fetch(video_id, languages=lang)
                break
            except: pass
        
        if not fetched:
            try:
                transcript_list = api.list(video_id)
                for tr in transcript_list:
                    fetched = tr.fetch()
                    break
            except: pass

        if not fetched: return "Error: Could not retrieve captions."
        
        if hasattr(fetched, 'to_raw_data'):
            return " ".join([item['text'] for item in fetched.to_raw_data() if 'text' in item])
        return " ".join([getattr(item, 'text', '') for item in fetched])
    except Exception as e:
        return f"Error extracting transcript: {e}"

def get_pdf_text(uploaded_file):
    try:
        reader = PyPDF2.PdfReader(uploaded_file)
        return "".join([page.extract_text() + "\n" for page in reader.pages if page.extract_text()])
    except Exception as e:
        return f"Error reading PDF: {e}"

def generate_quiz_batched(content, total_requested, api_keys):
    batch_size = 20
    total_batches = math.ceil(total_requested / batch_size)
    all_questions = []
    text_length = len(content)
    
    progress_bar = st.progress(0.0)
    status_text = st.empty()

    current_key_idx = 0
    client = genai.Client(api_key=api_keys[current_key_idx])

    for batch_idx in range(total_batches):
        current_batch_qty = min(batch_size, total_requested - len(all_questions))
        start_char = int((batch_idx / total_batches) * text_length)
        end_char = int(((batch_idx + 1) / total_batches) * text_length)
        content_slice = content[start_char:min(end_char + 15000, text_length)]
        
        status_text.text(f"⚡ Processing batch {batch_idx + 1} of {total_batches} (Using API Key {current_key_idx + 1}/{len(api_keys)})...")
        progress_bar.progress(batch_idx / total_batches)

        prompt = f"""
        You are an expert CLAT and AILET legal and current affairs examiner. 
        Based ONLY on the following study material segment, generate exactly {current_batch_qty} high-yield flashcard MCQs.
        
        Return ONLY a JSON array adhering strictly to this schema:
        [
          {{
            "category": "Legal Affairs / Polity / National / International / Environment",
            "question": "Question text here",
            "options": {{
              "A": "Option A text",
              "B": "Option B text",
              "C": "Option C text",
              "D": "Option D text"
            }},
            "correct_answer": "A",
            "explanation": "Detailed explanation note highlighting key facts for CLAT."
          }}
        ]

        Study Material Segment:
        {content_slice}
        """

        success = False
        attempts = 0
        
        while not success and attempts < len(api_keys):
            try:
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config={'response_mime_type': 'application/json'}
                )
                batch_data = json.loads(response.text)
                if isinstance(batch_data, list):
                    all_questions.extend(batch_data)
                success = True
                
            except Exception as e:
                error_str = str(e).lower()
                if any(kw in error_str for kw in ["429", "quota", "exhausted", "limit", "too many"]):
                    attempts += 1
                    if attempts < len(api_keys):
                        current_key_idx = (current_key_idx + 1) % len(api_keys)
                        status_text.text(f"⚠️ Quota reached. Auto-switching to API Key {current_key_idx + 1}...")
                        client = genai.Client(api_key=api_keys[current_key_idx])
                    else:
                        st.error("❌ All provided API keys have exhausted their quotas.")
                        break
                else:
                    st.error(f"Generation error on batch {batch_idx + 1}: {e}")
                    break

        if not success: break

    progress_bar.progress(1.0)
    status_text.empty()
    progress_bar.empty()
    return all_questions[:total_requested]

# ==========================================
# STREAMLIT USER INTERFACE
# ==========================================

st.set_page_config(page_title="NotebookLM Flashcard Hub", page_icon="📘", layout="wide")
apply_notebooklm_css()

if "quiz_data" not in st.session_state: st.session_state.quiz_data = None
if "current_idx" not in st.session_state: st.session_state.current_idx = 0
if "user_answers" not in st.session_state: st.session_state.user_answers = {}
if "is_finished" not in st.session_state: st.session_state.is_finished = False
if "start_time" not in st.session_state: st.session_state.start_time = None
if "end_time" not in st.session_state: st.session_state.end_time = None

st.title("📘 NotebookLM Interactive Quiz Hub")
st.markdown("Transform long lectures & current affairs PDFs into structured flashcard decks.")

st.sidebar.header("⚙️ Configuration")
api_keys_input = st.sidebar.text_area(
    "Gemini API Keys (One per line)", 
    help="Paste multiple API keys here. The app will automatically switch keys if one hits a quota limit."
)
api_keys_list = [k.strip() for k in api_keys_input.split('\n') if k.strip()]

num_questions = st.sidebar.number_input(
    "Number of Questions (1 - 1,500)", min_value=5, max_value=1500, value=20, step=5
)

source_type = st.radio("Select source material:", ["YouTube Video", "PDF Document"])
content_text = ""
video_id = None

if source_type == "YouTube Video":
    yt_url = st.text_input("🔗 Paste YouTube Video URL:")
    if yt_url:
        video_id = extract_youtube_id(yt_url)
        if not video_id: st.error("Invalid YouTube URL.")
        else: st.image(f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg", width=360)
elif source_type == "PDF Document":
    uploaded_file = st.file_uploader("📄 Upload Current Affairs PDF", type=["pdf"])

if st.button("🚀 Generate Quiz Deck", type="primary", use_container_width=True):
    if not api_keys_list:
        st.warning("⚠️ Please enter at least one Gemini API Key in the sidebar.")
        st.stop()

    with st.spinner("Extracting material text..."):
        if source_type == "YouTube Video" and yt_url and video_id: content_text = get_youtube_transcript(video_id)
        elif source_type == "PDF Document" and uploaded_file: content_text = get_pdf_text(uploaded_file)
        else:
            st.warning("Please provide a valid source file or URL.")
            st.stop()

        if content_text.startswith("Error"):
            st.error(content_text)
            st.stop()

        try:
            quiz_results = generate_quiz_batched(content_text, num_questions, api_keys_list)
            if quiz_results:
                st.session_state.quiz_data = quiz_results
                st.session_state.current_idx = 0
                st.session_state.user_answers = {}
                st.session_state.is_finished = False
                st.session_state.start_time = time.time() 
                st.rerun()
            else: st.error("Failed to extract questions from content.")
        except Exception as e:
            st.error(f"Error generating quiz: {e}")

# ==========================================
# QUIZ INTERFACE & DASHBOARD
# ==========================================

if st.session_state.quiz_data:
    quiz_data = st.session_state.quiz_data
    total_q = len(quiz_data)

    if not st.session_state.is_finished:
        curr_i = st.session_state.current_idx
        q = quiz_data[curr_i]

        st.markdown("---")
        
        # UI Header with Progress and LIVE TIMER
        col_title, col_prog, col_timer = st.columns([2, 3, 1])
        with col_title: 
            st.caption(f"Flashcard {curr_i + 1} of {total_q}")
        with col_prog: 
            st.progress((curr_i + 1) / total_q)
        with col_timer:
            # Inject Live JavaScript Timer
            start_ms = int(st.session_state.start_time * 1000)
            components.html(f"""
            <div style="font-family: 'Google Sans', sans-serif; font-size: 14px; font-weight: 600; color: #0b57d0; text-align: right;">
                ⏱️ <span id="clock">0m 0s</span>
            </div>
            <script>
                var start_time = {start_ms};
                setInterval(function() {{
                    var delta = Math.floor((Date.now() - start_time) / 1000);
                    var m = Math.floor(delta / 60);
                    var s = delta % 60;
                    document.getElementById("clock").innerHTML = m + "m " + s + "s";
                }}, 1000);
            </script>
            """, height=30)

        # Question Surface Card
        with st.container(border=True):
            category = q.get("category", "Current Affairs")
            st.markdown(f'<span class="category-badge">{category}</span>', unsafe_allow_html=True)
            st.markdown(f"### **{q['question']}**")

            options = q["options"]
            formatted_options = [f"{key}) {val}" for key, val in options.items()]

            saved_choice_idx = None
            if curr_i in st.session_state.user_answers:
                chosen_k = st.session_state.user_answers[curr_i]
                saved_choice_idx = list(options.keys()).index(chosen_k)

            selected_option = st.radio(
                label=f"Options for Card {curr_i + 1}",
                options=formatted_options,
                index=saved_choice_idx,
                key=f"q_radio_{curr_i}",
                label_visibility="collapsed"
            )

            if selected_option:
                chosen_key = selected_option.split(")")[0].strip()
                st.session_state.user_answers[curr_i] = chosen_key
                correct_key = q["correct_answer"]
                correct_text = options[correct_key]

                if chosen_key == correct_key:
                    st.markdown(f'<div class="correct-box">🎯 <strong>Correct!</strong> Option {correct_key}) {correct_text}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="incorrect-box">❌ <strong>Incorrect.</strong> Correct answer is <strong>{correct_key}) {correct_text}</strong></div>', unsafe_allow_html=True)

                st.markdown(f'<div class="explanation-box">💡 <strong>Key Takeaway & Explanation:</strong><br>{q["explanation"]}</div>', unsafe_allow_html=True)

        # Navigation Controls
        c_prev, c_center, c_next = st.columns([1, 2, 1])
        with c_prev:
            if curr_i > 0:
                if st.button("⬅️ Previous Card", use_container_width=True):
                    st.session_state.current_idx -= 1
                    st.rerun()
        with c_next:
            if curr_i < total_q - 1:
                if st.button("Next Card ➡️", type="primary", use_container_width=True):
                    st.session_state.current_idx += 1
                    st.rerun()
            else:
                if st.button("📊 Finish & View Dashboard", type="primary", use_container_width=True):
                    st.session_state.is_finished = True
                    st.session_state.end_time = time.time()
                    st.rerun()

    # ------------------------------------------
    # VIEW 2: NOTEBOOKLM DASHBOARD & REVIEW DECK
    # ------------------------------------------
    else:
        st.markdown("---")
        st.subheader("📊 Performance & Study Summary")

        correct_count = sum(1 for idx, q in enumerate(quiz_data) if st.session_state.user_answers.get(idx) == q["correct_answer"])
        accuracy = (correct_count / total_q) * 100 if total_q > 0 else 0

        time_str = "N/A"
        if st.session_state.start_time and st.session_state.end_time:
            time_taken = st.session_state.end_time - st.session_state.start_time
            mins, secs = divmod(int(time_taken), 60)
            time_str = f"{mins}m {secs}s"

        m1, m2, m3, m4 = st.columns(4)
        with m1: st.metric("Total Score", f"{correct_count} / {total_q}")
        with m2: st.metric("Accuracy", f"{accuracy:.1f}%")
        with m3: st.metric("Total Time", time_str)
        with m4: 
            status = "Target Achieved 🎉" if accuracy >= 70 else "Needs Revision 📚"
            st.metric("Readiness Level", status)

        if accuracy >= 80: st.balloons()

        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("🔍 Complete Question Review Deck")

        for idx, q in enumerate(quiz_data):
            user_choice = st.session_state.user_answers.get(idx)
            correct_choice = q["correct_answer"]
            options = q["options"]

            with st.container(border=True):
                category = q.get("category", "Current Affairs")
                st.markdown(f'<span class="category-badge">{category}</span>', unsafe_allow_html=True)
                st.markdown(f"**{idx + 1}. {q['question']}**")

                if user_choice == correct_choice:
                    st.markdown(f"✅ **Your Answer:** {user_choice}) {options[user_choice]} *(Correct)*")
                else:
                    user_str = f"{user_choice}) {options[user_choice]}" if user_choice in options else "Unanswered"
                    st.markdown(f"❌ **Your Answer:** {user_str}")
                    st.markdown(f"🟢 **Correct Answer:** {correct_choice}) {options[correct_choice]}")

                st.markdown(f'<div class="explanation-box">💡 <strong>Explanation:</strong> {q["explanation"]}</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Start New Session", type="primary", use_container_width=True):
            st.session_state.quiz_data = None
            st.session_state.current_idx = 0
            st.session_state.user_answers = {}
            st.session_state.is_finished = False
            st.session_state.start_time = None
            st.session_state.end_time = None
            st.rerun()
