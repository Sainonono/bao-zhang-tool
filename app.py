import streamlit as st
from docxtpl import DocxTemplate
import re, io, datetime, random
from collections import Counter

# --- 1. 智能数据清洗 ---
def parse_menu_text(text):
    items = []
    lines = text.strip().split('\n')
    for line in lines:
        line = line.strip().replace('\x07', ' ')
        if not line: continue
        nums = re.findall(r'\d+\.?\d*', line)
        name_part = re.sub(r'\d+\.?\d*', '', line).replace('元/串', '').replace('元/份', '').strip()
        if name_part and len(nums) >= 1:
            price = float(nums[0])
            items.append({"name": name_part, "price": price})
    # 去重
    unique_items = {i['name']: i for i in items}.values()
    return list(unique_items)

# --- 2. 核心算法：确保“至少 N 种”菜品 ---
def get_best_combo_with_min_types(items, target_amount, max_qty, min_types):
    # 放大10倍处理
    target_int = int(round(target_amount * 10))
    
    # 1. 随机挑选 min_types 种菜作为“必选底色”
    if len(items) < min_types:
        min_types = len(items)
    
    # 尝试 20 次随机初始化，寻找最精准的解
    best_overall_selected = []
    best_overall_sum = 0

    for _ in range(20):
        must_have_items = random.sample(items, min_types)
        current_sum = sum(int(round(i['price'] * 10)) for i in must_have_items)
        
        # 如果必选菜的总价已经超过目标，则跳过这次尝试
        if current_sum > target_int:
            continue
            
        remaining_target = target_int - current_sum
        
        # 2. 对剩余金额进行动态规划（限制在已选的种类或者全部种类中）
        dp = [None] * (remaining_target + 1)
        dp[0] = []
        
        for item in items:
            price = int(round(item['price'] * 10))
            if price <= 0: continue
            # 限制剩余部分每样菜最多还能点多少份
            for _ in range(max_qty - 1): 
                for i in range(remaining_target, price - 1, -1):
                    if dp[i - price] is not None:
                        new_combo = dp[i - price] + [item]
                        if dp[i] is None or len(new_combo) < len(dp[i]):
                            dp[i] = new_combo
        
        # 寻找这一轮最接近的结果
        for i in range(remaining_target, -1, -1):
            if dp[i] is not None:
                total_res = must_have_items + dp[i]
                actual_sum = i + current_sum
                if actual_sum > best_overall_sum:
                    best_overall_sum = actual_sum
                    best_overall_selected = total_res
                break
                
    return best_overall_selected, best_overall_sum / 10.0

# --- 3. Streamlit UI 界面 ---
st.set_page_config(page_title="金融级凑单工具-最终版", layout="wide")
st.title("⚖️ 报账菜单自动生成器 (全手动约束版)")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📌 基础信息与约束")
    shop_name = st.text_input("店名", "皮兄烧烤")
    address = st.text_input("用餐地址", "乐山市市中区平贤路")
    dining_time = st.text_input("用餐时间", value=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    people_count = st.number_input("用餐人数", value=4, min_value=1)
    target_amount = st.number_input("目标报账总额 (元)", value=430.0)
    
    st.divider()
    
    c1, c2, c3 = st.columns(3)
    with c1:
        max_price_limit = st.number_input("菜品最高限价", value=300)
    with c2:
        user_max_qty = st.number_input("单菜数量上限", value=30, min_value=1)
    with c3:
        # 核心改动：至少出现多少种菜
        min_types = st.number_input("至少出现菜品种类", value=10, min_value=1, max_value=21)

with col2:
    st.subheader("📋 粘贴原始菜单")
    raw_menu = st.text_area("请在这里粘贴菜单内容", height=380)

# --- 4. 执行与导出 ---
if st.button("🚀 开始生成报账单", type="primary"):
    if not raw_menu:
        st.error("❌ 请先粘贴菜单内容！")
    else:
        all_items = parse_menu_text(raw_menu)
        filtered_items = [i for i in all_items if i['price'] <= max_price_limit]
        
        if len(filtered_items) < min_types:
            st.error(f"❌ 错误：合格菜品仅 {len(filtered_items)} 种，无法满足“至少 {min_types} 种”的要求，请降低要求或增加菜单。")
        else:
            # 执行计算
            selected_raw, total_sum = get_best_combo_with_min_types(filtered_items, target_amount, user_max_qty, min_types)
            
            if not selected_raw:
                st.warning("⚠️ 无法匹配目标金额，请调整参数。")
            else:
                # 聚合
                counts = Counter([i['name'] for i in selected_raw])
                price_map = {i['name']: i['price'] for i in selected_raw}
                final_items = []
                for name, qty in counts.items():
                    final_items.append({
                        "name": name, "qty": qty, "price": price_map[name], 
                        "subtotal": round(qty * price_map[name], 2)
                    })

                st.success(f"✅ 成功凑齐！总额：{total_sum} 元 (包含 {len(final_items)} 种菜品)")
                st.table(final_items)

                # --- Word 渲染 ---
                try:
                    doc = DocxTemplate("template.docx")
                    context = {
                        'shop_name': shop_name, 'address': address, 'people': people_count,
                        'time': dining_time, 'total': total_sum
                    }
                    # 填充 21 行
                    for i in range(1, 22):
                        if i <= len(final_items):
                            item = final_items[i-1]
                            context[f'n{i}'] = item['name']
                            context[f'q{i}'] = item['qty']
                            context[f'p{i}'] = item['price']
                            context[f't{i}'] = item['subtotal']
                        else:
                            context[f'n{i}'] = "DELETE_ROW"
                            context[f'q{i}'] = context[f'p{i}'] = context[f't{i}'] = ""

                    doc.render(context)
                    # 物理删行
                    docx_obj = doc.docx
                    for table in docx_obj.tables:
                        for row in list(table.rows):
                            if "DELETE_ROW" in row.cells[0].text:
                                row._tr.getparent().remove(row._tr)
                    
                    bio = io.BytesIO()
                    doc.save(bio)
                    st.download_button("⬇️ 下载完美报账单", bio.getvalue(), f"{shop_name}_报账单.docx")
                except Exception as e:
                    st.error(f"❌ Word 导出失败: {e}")
