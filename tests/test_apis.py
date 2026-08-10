import os
import sys
# Force UTF-8 encoding for standard output on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
from openai import OpenAI
from google import genai
from dotenv import load_dotenv
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
import config


# Load env
load_dotenv()

def test_openai():
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    model = config.OPENAI_MODEL 
    
    if not api_key:
        print("❌ OpenAI: API Key tidak ditemukan di .env")
        return False
        
    print(f"🔄 OpenAI: Mencoba memanggil {model}...")
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say 'OpenAI OK' in one line."}],
            max_completion_tokens=128
        )
        result = response.choices[0].message.content.strip()
        print(f"✅ OpenAI Sukses: '{result}'")
        return True
    except Exception as e:
        print(f"❌ OpenAI Gagal: {e}")
        return False

def test_gemini():
    api_key = os.getenv("GEMINI_API_KEY")
    model = config.GEMINI_MODEL # use cheap model for testing
    
    if not api_key:
        print("❌ Gemini: API Key tidak ditemukan di .env")
        return False
        
    print(f"🔄 Gemini: Mencoba memanggil {model}...")
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents="Say 'Gemini OK' in one line."
        )
        result = response.text.strip()
        print(f"✅ Gemini Sukses: '{result}'")
        return True
    except Exception as e:
        print(f"❌ Gemini Gagal: {e}")
        return False

def test_claude():
    model = config.CLAUDE_MODEL

    if model.startswith("deepseek/"):
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            print("❌ DeepSeek: API Key tidak ditemukan di .env")
            return False
        print(f"🔄 DeepSeek: Mencoba memanggil {model}...")
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=config.DEEPSEEK_API_BASE)
            response = client.chat.completions.create(
                model=model.split("/", 1)[1],
                max_tokens=128,
                messages=[{"role": "user", "content": "Say 'DeepSeek OK' in one line."}],
            )
            result = response.choices[0].message.content.strip()
            print(f"✅ DeepSeek Sukses: '{result}'")
            return True
        except Exception as e:
            print(f"❌ DeepSeek Gagal: {e}")
            return False

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ Claude: API Key tidak ditemukan di .env")
        return False

    print(f"🔄 Claude: Mencoba memanggil {model}...")
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=128,
            messages=[{"role": "user", "content": "Say 'Claude OK' in one line."}],
        )
        result = "".join(b.text for b in response.content if b.type == "text").strip()
        print(f"✅ Claude Sukses: '{result}'")
        return True
    except Exception as e:
        print(f"❌ Claude Gagal: {e}")
        return False

if __name__ == "__main__":
    print("="*60)
    print("            PENGUJIAN KONEKSI API MULTI-LLM           ")
    print("="*60)
    
    openai_ok = test_openai()
    print("-" * 60)
    gemini_ok = test_gemini()
    print("-" * 60)
    claude_ok = test_claude()
    print("="*60)
    
    if openai_ok and gemini_ok and claude_ok:
        print("🎉 Semua API terhubung dengan sukses! Anda siap menjalankan bot.")
    else:
        print("⚠️ Beberapa API gagal terhubung. Silakan periksa kunci API Anda di file .env")
    print("="*60)
