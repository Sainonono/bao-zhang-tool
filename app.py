import streamlit as st
from docxtpl import DocxTemplate
import re
import io
import datetime
from collections import Counter

# --- 1. 智能数据清洗 (支持小数如 1.5元) ---
def parse_menu_text(text):
    items = []
    lines = text.strip().split('\n')
    for line in lines:
        line = line.strip().replace('\x07', ' ')
        if not line: continue
        
        # 提取数字（支持浮点数，如 1.5）
        nums = re.findall(r'\d+\.?\d*', line)
        # 提取菜名
        name_part = re.sub(r'\d+\.?\d*', '', line).replace('元/串', '').replace('元/份', '').strip()
        
        if name_part and len(nums) >= 1:
            price = float(nums[0])
            items.append({"name": name_part, "price": price})
            
    return items

# --- 2. 多重背包凑单算法 (支持数量上限 & 浮点数精度处理) ---
def get_best_combo_bounded(items, target_amount, max_qty_per_item):
    # 将目标金额和单价放大 10 倍（转化为整数运算，完美处理 1.5 元这种单价）
    target = int(round(target_amount * 10))
    
    dp = [None] * (target + 1)
    dp[0] = []
    
    for item in items:
        price = int(round(item['price'] * 10))
        if price <= 0: continue
        
        # 限制每道菜最多点 max_qty_per_item 份
        for _ in range(max_qty_per_item):
            for i in range(target, price - 1, -1):
                if dp[i - price] is not None:
                    new_combo = dp[i - price] + [item]
                    if dp[i] is None or len(new_combo) < len(dp[i]):
                        dp[i] = new_combo
                        
    # 寻找最接近目标的解
    for i in range(target, -1, -1):
        if dp[i] is not None:
            actual_sum = sum(x['price'] for x in dp[i])
            return dp[i], actual_sum
    return [], 0

# --- 3. Streamlit 界面配置 ---
st.set_page_config(page_title="烧烤/小吃凑单终极版", layout="wide")
st.title("🍢 金融级凑单工具 (自适应数量限制版)")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📌 基础信息")
    shop_name = st.text_input("店名", "皮兄烧烤")
    target_amount = st.number_input("目标金额", value=430)
    
    col_a, col_b = st.columns(2)
    with col_a:
        max_price_limit = st.number_input("单道菜最高限价", value=300)
    with col_b:
        # 这里就是你可以手动调整的数量限制框！
        user_max_qty = st.number_input("单道菜数量上限 (份)", value=10, min_value=1)

with col2:
    st.subheader("📋 粘贴菜单")
    raw_menu = st.text_area("请在这里粘贴菜单内容", height=230)

# --- 4. 核心逻辑 ---
if st.button("🚀 开始智能凑单并生成 Word", type="primary"):
    if not raw_menu:
        st.error("❌ 请输入菜单内容")
    else:
        raw_items = parse_menu_text(raw_menu)
        extracted_items = [item for item in raw_items if item['price'] <= max_price_limit]
        
        if not extracted_items:
            st.error("❌ 过滤失败：菜单里没有合格的菜品！")
        else:
            # 智能检测：如果都是便宜小吃，自动放宽上限，否则使用用户设定的上限
            highest_menu_price = max([item['price'] for item in extracted_items])
            if highest_menu_price <= 15:
                actual_max_qty = 50
                st.info(f"💡 触发【小吃模式】：菜单最高单价仅 {highest_menu_price} 元，为保证能凑够总额，已临时将上限调至 50 份。")
            else:
                actual_max_qty = user_max_qty
                
            # 计算组合
            selected_raw, total_sum = get_best_combo_bounded(extracted_items, target_amount, actual_max_qty)
            
            if not selected_raw:
                st.warning("⚠️ 无法凑出目标金额，请尝试降低金额或提供更多菜品。")
            else:
                # 聚合重复菜品（合并数量和总价）
                counts = Counter([item['name'] for item in selected_raw])
                price_map = {item['name']: item['price'] for item in selected_raw}
                
                final_items = []
                for name, qty in counts.items():
                    final_items.append({
                        "name": name,
                        "qty": qty,
                        "price": price_map[name],
                        "subtotal": round(qty * price_map[name], 2)
                    })

                st.success(f"✅ 计算完成！最优组合：{total_sum} 元 (包含 {len(final_items)} 种菜品)")
                st.table(final_items)

                # --- 渲染 Word ---
                try:
                    doc = DocxTemplate("template.docx")
                    
                    context = {
                        'shop_name': shop_name,
                        'total': total_sum,
                        'time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    
                    # 填充 21 行数据
                    MAX_ROWS = 21 
                    for i in range(1, MAX_ROWS + 1):
                        if i <= len(final_items):
                            item = final_items[i-1]
                            context[f'n{i}'] = item['name']
                            context[f'q{i}'] = item['qty']
                            context[f'p{i}'] = item['price']
                            context[f't{i}'] = item['subtotal']
                        else:
                            # 多余的行打上删除标记
                            context[f'n{i}'] = "DELETE_ROW"
                            context[f'q{i}'] = ""
                            context[f'p{i}'] = ""
                            context[f't{i}'] = ""

                    doc.render(context)
                    
                    # 物理切除带有 DELETE_ROW 标记的行
                    docx_obj = doc.docx if hasattr(doc, 'docx') else doc 
                    for table in docx_obj.tables:
                        for row in list(table.rows):
                            if "DELETE_ROW" in row.cells[0].text:
                                row._tr.getparent().remove(row._tr)
                    
                    bio = io.BytesIO()
                    doc.save(bio)
                    st.download_button(
                        label="⬇️ 点击下载自动排版的报账单",
                        data=bio.getvalue(),
                        file_name=f"{shop_name}_报账单.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                except Exception as e:
                    st.error(f"❌ Word 渲染失败！底层报错: {e}")
