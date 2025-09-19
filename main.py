import feedparser
import os
import time
import re
import requests
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium_stealth import stealth

# --- برمجة ahmed si ---

RSS_URL = "https://Fastyummyfood.com/feed"
POSTED_LINKS_FILE = "posted_links.txt"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

def get_posted_links():
    if not os.path.exists(POSTED_LINKS_FILE): return set()
    with open(POSTED_LINKS_FILE, "r", encoding='utf-8') as f: return set(line.strip() for line in f)

def add_posted_link(link):
    with open(POSTED_LINKS_FILE, "a", encoding='utf-8') as f: f.write(link + "\n")

def get_next_post_to_publish():
    print(f"--- 1. البحث عن مقالات في: {RSS_URL}")
    feed = feedparser.parse(RSS_URL)
    if not feed.entries: return None
    print(f"--- تم العثور على {len(feed.entries)} مقالات.")
    posted_links = get_posted_links()
    for entry in reversed(feed.entries):
        if entry.link not in posted_links:
            print(f">>> تم تحديد المقال: {entry.title}")
            return entry
    return None

def extract_image_url_from_entry(entry):
    if hasattr(entry, 'media_content') and entry.media_content:
        for media in entry.media_content:
            if 'url' in media and media.get('medium') == 'image': return media['url']
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enclosure in entry.enclosures:
            if 'href' in enclosure and 'image' in enclosure.get('type', ''): return enclosure.href
    content_html = ""
    if 'content' in entry and entry.content: content_html = entry.content[0].value
    else: content_html = entry.summary
    match = re.search(r'<img[^>]+src="([^">]+)"', content_html)
    if match: return match.group(1)
    return None

def rewrite_content_with_gemini(title, content_html, original_link, image_url):
    # (هذه الدالة تبقى كما هي، لا تغيير)
    if not GEMINI_API_KEY:
        print("!!! تحذير: لم يتم العثور على مفتاح GEMINI_API_KEY.")
        return None
    print("--- 💬 التواصل مع Gemini API لإنشاء مقال احترافي...")
    clean_content = re.sub('<[^<]+?>', ' ', content_html)
    prompt = f"""
    You are a professional SEO copywriter for Medium.
    Your task is to take an original recipe title and content, and write a full Medium-style article (around 600 words) optimized for SEO, engagement, and backlinks.
    **Original Data:**
    - Original Title: "{title}"
    - Original Content Snippet: "{clean_content[:1500]}"
    - Link to the full recipe: "{original_link}"
    - Available Image URL: "{image_url}"
    **Article Requirements:**
    1.  **Focus Keyword:** Identify the main focus keyword from the original title.
    2.  **Title:** Create a new title using the Hybrid Headline strategy.
    3.  **Article Body (HTML Format):**
        - Write a 600-700 word article in clean HTML.
        - **Image Placement:** Crucially, you MUST insert two image placeholders exactly as written below:
            - `<!-- IMAGE 1 PLACEHOLDER -->` after the intro.
            - `<!-- IMAGE 2 PLACEHOLDER -->` before the listicle section.
            Do not add your own `<img>` tags.
    4.  **Smart Closing Method...**
    **Output Format:**
    Return ONLY a valid JSON object with the keys: "new_title", "new_html_content", "tags", and "alt_texts".
    """
    api_url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}'
    headers = {'Content-Type': 'application/json'}
    data = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": 4096}}
    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(data), timeout=180)
        response.raise_for_status()
        response_json = response.json()
        raw_text = response_json['candidates'][0]['content']['parts'][0]['text']
        json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if json_match:
            clean_json_str = json_match.group(0)
            result = json.loads(clean_json_str)
            print("--- ✅ تم استلام مقال كامل من Gemini.")
            return {"title": result.get("new_title", title), "content": result.get("new_html_content", content_html), "tags": result.get("tags", []), "alt_texts": result.get("alt_texts", [])}
        else: raise ValueError("JSON not found in Gemini response")
    except Exception as e:
        print(f"!!! Error communicating with Gemini: {e}")
        return None

# --- *** دالة مساعدة جديدة لإضافة الصور *** ---
def add_image_and_caption(driver, wait, image_url, caption_text):
    try:
        print(f"--- 📸 محاولة إضافة صورة من الرابط: {image_url}")
        # الضغط على زر الإضافة (+) الذي يظهر على سطر جديد
        plus_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-action="open-embed-bar"]')))
        plus_button.click()
        time.sleep(1)

        # الضغط على زر "إضافة صورة من رابط" (أيقونة الكاميرا)
        add_from_link_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@data-action='embed-image']")))
        add_from_link_button.click()
        time.sleep(1)

        # إدخال رابط الصورة والضغط على Enter
        link_input = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[placeholder*="Paste a link"]')))
        link_input.send_keys(image_url)
        link_input.send_keys(Keys.ENTER)
        
        # انتظار ظهور الصورة ثم كتابة التعليق
        print("--- ✍️ كتابة التعليق على الصورة...")
        caption_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'figcaption[data-testid="imageCaption"]')))
        caption_field.click()
        caption_field.send_keys(caption_text)
        print("--- ✅ تمت إضافة الصورة والتعليق بنجاح.")
        # العودة إلى السطر الرئيسي للكتابة
        driver.find_element(By.CSS_SELECTOR, 'h3[data-testid="editorTitleParagraph"]').click()
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.CONTROL, Keys.END)
        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ENTER)
        
    except Exception as e:
        print(f"!!! حدث خطأ أثناء إضافة الصورة: {e}")
        # إذا فشل، اضغط Enter للمتابعة على الأقل
        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ENTER)

def paste_html_content(driver, html_content):
    js_script = "const html = arguments[0]; const blob = new Blob([html], { type: 'text/html' }); const item = new ClipboardItem({ 'text/html': blob }); navigator.clipboard.write([item]);"
    driver.execute_script(js_script, html_content)
    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.CONTROL, 'v')
    time.sleep(2)

def main():
    print("--- بدء تشغيل الروبوت الناشر v22 (نسخة المحاكاة البشرية) ---")
    post_to_publish = get_next_post_to_publish()
    if not post_to_publish:
        print(">>> النتيجة: لا توجد مقالات جديدة.")
        return

    original_title = post_to_publish.title
    original_link = post_to_publish.link
    image_url = extract_image_url_from_entry(post_to_publish)
    if image_url: print(f"--- 🖼️ تم العثور على رابط الصورة: {image_url}")
    else: print("--- ⚠️ لم يتم العثور على رابط صورة في RSS لهذا المقال.")
    
    original_content_html = post_to_publish.summary
    if 'content' in post_to_publish and post_to_publish.content:
        original_content_html = post_to_publish.content[0].value

    rewritten_data = rewrite_content_with_gemini(original_title, original_content_html, original_link, image_url)
    
    sid_cookie = os.environ.get("MEDIUM_SID_COOKIE")
    uid_cookie = os.environ.get("MEDIUM_UID_COOKIE")
    if not sid_cookie or not uid_cookie:
        print("!!! خطأ: لم يتم العثور على الكوكيز.")
        return

    options = webdriver.ChromeOptions()
    # (إعدادات المتصفح)
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("window-size=1920,1080")

    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    stealth(driver, languages=["en-US", "en"], vendor="Google Inc.", platform="Win32", webgl_vendor="Intel Inc.", renderer="Intel Iris OpenGL Engine", fix_hairline=True)

    try:
        print("--- 2. إعداد الجلسة...")
        driver.get("https://medium.com/")
        driver.add_cookie({"name": "sid", "value": sid_cookie, "domain": ".medium.com"})
        driver.add_cookie({"name": "uid", "value": uid_cookie, "domain": ".medium.com"})
        
        print("--- 3. الانتقال إلى محرر المقالات...")
        driver.get("https://medium.com/new-story")
        wait = WebDriverWait(driver, 30)

        # --- *** منطق النشر الجديد *** ---
        print("--- 4. بدء عملية النشر بطريقة المحاكاة البشرية...")
        
        if rewritten_data:
            final_title = rewritten_data["title"]
            generated_html_content = rewritten_data["content"]
            ai_tags = rewritten_data.get("tags", [])
            ai_alt_texts = rewritten_data.get("alt_texts", [])
            
            # كتابة العنوان
            title_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'h3[data-testid="editorTitleParagraph"]')))
            title_field.click()
            title_field.send_keys(final_title)
            
            story_field_selector = 'p[data-testid="editorParagraphText"]'
            wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, story_field_selector))).click()

            # تقسيم المحتوى حول علامات الصور
            parts = re.split(r'<!-- IMAGE \d PLACEHOLDER -->', generated_html_content)
            
            # لصق الجزء الأول من النص
            paste_html_content(driver, parts[0])
            
            # إضافة الصورة الأولى إذا وجدت
            if image_url and len(parts) > 1:
                alt_text1 = ai_alt_texts[0] if len(ai_alt_texts) > 0 else "Recipe main image"
                site_name = re.search(r'https?://(?:www\.)?([^/]+)', original_link).group(1) if re.search(r'https?://', original_link) else "our website"
                caption1 = f"{alt_text1} - {site_name}"
                add_image_and_caption(driver, wait, image_url, caption1)

            # لصق الجزء الثاني من النص
            if len(parts) > 1:
                paste_html_content(driver, parts[1])
            
            # إضافة الصورة الثانية إذا وجدت
            if image_url and len(parts) > 2:
                alt_text2 = ai_alt_texts[1] if len(ai_alt_texts) > 1 else "Detailed view of the recipe"
                site_name = re.search(r'https?://(?:www\.)?([^/]+)', original_link).group(1) if re.search(r'https?://', original_link) else "our website"
                caption2 = f"{alt_text2} - {site_name}"
                add_image_and_caption(driver, wait, image_url, caption2)
            
            # لصق الجزء المتبقي من النص
            if len(parts) > 2:
                paste_html_content(driver, parts[2])
        else:
            # الخطة البديلة في حال فشل Gemini
            print("--- سيتم استخدام المحتوى الأصلي.")
            title_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'h3[data-testid="editorTitleParagraph"]')))
            title_field.click()
            title_field.send_keys(original_title)
            story_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'p[data-testid="editorParagraphText"]')))
            story_field.click()
            image_html = f'<img src="{image_url}">' if image_url else ""
            paste_html_content(driver, image_html + original_content_html)
            ai_tags = []

        # (بقية الكود للنشر وإضافة الوسوم يبقى كما هو)
        print("--- 5. بدء عملية النشر...")
        publish_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-action="show-prepublish"]')))
        publish_button.click()

        print("--- 6. إضافة الوسوم المتاحة...")
        final_tags = ai_tags[:5] if ai_tags else []
        if final_tags:
            tags_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="publishTopicsInput"]')))
            tags_input.click()
            for tag in final_tags: tags_input.send_keys(tag); time.sleep(0.5); tags_input.send_keys(Keys.ENTER); time.sleep(1)
            print(f"--- تمت إضافة الوسوم: {', '.join(final_tags)}")
        else: print("--- لا توجد وسوم لإضافتها.")

        print("--- 7. إرسال أمر النشر النهائي...")
        publish_now_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="publishConfirmButton"]')))
        time.sleep(2)
        driver.execute_script("arguments[0].click();", publish_now_button)

        print("--- 8. انتظار نهائي للسماح بمعالجة النشر...")
        time.sleep(15)
        add_posted_link(post_to_publish.link)
        print(">>> 🎉🎉🎉 تم نشر المقال بنجاح! 🎉🎉🎉")
    except Exception as e:
        print(f"!!! حدث خطأ فادح: {e}")
        driver.save_screenshot("error_screenshot.png")
        with open("error_page_source.html", "w", encoding="utf-8") as f: f.write(driver.page_source)
        raise e
    finally:
        driver.quit()
        print("--- تم إغلاق الروبوت ---")

if __name__ == "__main__":
    main()
