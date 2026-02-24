import os
import praw
from openai import OpenAI
import yagmail
from datetime import datetime
from dotenv import load_dotenv  
load_dotenv()                  

 
# --- 配置从 GitHub Secrets 获取 ---
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

# 初始化客户端
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent="ML_Digest_Bot/0.1"
)
ai_client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

def get_reddit_posts(subreddit_name, limit=30):
    print(f"正在从 r/{subreddit_name} 获取帖子...")
    subreddit = reddit.subreddit(subreddit_name)
    posts = []
    # 获取过去24小时最热的25个帖子
    for post in subreddit.top(time_filter="week", limit=limit):
        if post.is_self: # 只看文本讨论帖，避免纯链接
            posts.append({
                "subreddit": subreddit_name,
                "title": post.title,
                "content": post.selftext[:10000], # 截取前2000字
                "url": f"https://www.reddit.com{post.permalink}",
                "score": post.score
            })
    return posts

def evaluate_post(post):
    print(f"正在 AI 评估: {post['title'][:30]}...")
    prompt = f"""
    ### Role
    You are a Senior Machine Learning Researcher at a top-tier institution. Your task is to critically evaluate Reddit posts from r/MachineLearning to identify high-value research, significant technical breakthroughs, or profound engineering insights.

    ### Input Data
    - **Title**: {post['title']}
    - **Content**: {post['content']}

    ### Evaluation Criteria
    1. **Originality**: Does it present new ideas, libraries, or papers?
    2. **Technical Depth**: Is the content rigorous or just surface-level?
    3. **Practical Value**: Can this be applied to real-world ML problems or research?
    4. **Signal-to-Noise**: Is it a high-quality discussion or a repetitive/low-effort post?

    ### Instructions
    - First, analyze the content internally.
    - Then, output a strictly formatted JSON object.
    - The "summary" field MUST be in **Chinese** to ensure the final report is easy to read.
    - The "score" should be an integer from 1 to 10 (8+ means must-read).

    ### Output Format
    {{
        "analysis_brief": "A one-sentence internal reasoning in English",
        "score": 10,
        "summary": "100字以内的中文核心总结"
    }}
    """
    try:
        response = ai_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                # DeepSeek 建议增加一个 system role 来强化 JSON 输出稳定性
                {"role": "system", "content": "你是一个 JSON 助手，请严格按要求的 JSON 格式输出。"},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" }
        )
        import json
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"AI 评估出错: {e}")
        return {"score": 0, "summary": "评估失败"}

def main():
    target_subs = [
        "MachineLearning", 
        "ArtificialInteligence", 
        "LearnMachineLearning", 
        "ReinforcementLearning",
        "FAANGrecruiting"
    ]
    high_quality_posts = []
    
    for sub in target_subs:
        raw_posts = get_reddit_posts(sub, limit=50)

        for p in raw_posts:
            # 初步筛选：Reddit 点赞数超过 1 才送去 AI
            if p['score'] > 1:
                result = evaluate_post(p)
                if result['score'] >= 8:
                    p['summary'] = result['summary']
                    p['ai_score'] = result['score']
                    high_quality_posts.append(p)

    if not high_quality_posts:
        print("今日没有发现高质量帖子。")
        return

    # 构造邮件内容
    header = f"<h2>AI & ML 社区每周精选 ({datetime.now().strftime('%Y-%m-%d')})</h2>"
    header += f"<p>涵盖板块: {', '.join([f'r/{s}' for s in target_subs])}</p><hr>"
    sections = []
    
    for p in high_quality_posts:
        section = f"""
        <div style="margin-bottom: 25px; border-left: 4px solid #3498db; padding-left: 15px; font-family: sans-serif;">
            <span style="color: #e67e22; font-weight: bold;">[r/{p['subreddit']}]</span>
            <h3 style="margin-top: 5px;"><a href="{p['url']}" style="text-decoration: none; color: #2980b9;">{p['title']}</a></h3>
            <p style="color: #333; background: #f9f9f9; padding: 10px; border-radius: 4px;">
                <strong>AI 总结：</strong>{p['summary']}
            </p>
            <p style="color: #666; font-size: 0.85em;">
                AI 评分: <span style="color: #27ae60; font-weight: bold;">{p['ai_score']}</span> | 
                Reddit 点赞: {p['score']}
            </p>
        </div>
        """
        sections.append(section)

    # 将列表拼接成一个完整的 HTML 字符串
    full_html_body = header + "".join(sections)

    # 2. 发送邮件
    print(f"正在发送邮件 (共 {len(high_quality_posts)} 篇精选)...")
    try:
        yag = yagmail.SMTP(
            user=EMAIL_USER, 
            password=EMAIL_PASS,
            host='smtp.126.com'
        )
        # 将 contents 指向生成的完整字符串
        yag.send(
            to=RECEIVER_EMAIL, 
            subject=f"Reddit Weekly Digest: {len(high_quality_posts)} New Insights",
            contents=full_html_body
        )
        print("任务完成！")
    except Exception as e:
        print(f"邮件发送出错: {e}")

if __name__ == "__main__":
    main()
