import streamlit as st
from docxtpl import DocxTemplate
import re
import io
import datetime
from collections import Counter

# --- 1. 智能数据清洗 (支持 1.5元 等小数) ---
def parse_menu_text(text):
    items = []
    lines = text.strip().split('\n')
    for line in lines:
        line = line.strip().replace('\x07', ' ')
        if not line: continue
        
        # 匹配数字（包括 1.5 这种浮点数）
        nums = re.findall(r'\d+\.?\d*', line)
        # 提取菜名（过滤掉单价单位）
        name_part = re.sub(r'\d+\.?\d*', '', line).replace('元/串', '').replace('元/份', '').strip()
        
        if name_part and len(nums) >= 1:
            price = float(nums[0])
            items.append({"name": name_part, "price": price})
            
    return items

# --- 2. 核心算法：10倍精度放大 + 多重背包 ---
def get_best_combo_bounded(items, target_amount, max_qty_per_item):
    # 放大10倍处理 1.5元，转为整数运算防止精度丢失
    target = int(round(target_amount * 10))
    dp = [None] * (target + 1)
    dp[0] = []
    
    for item in items:
        price = int(round(item['price'] * 10))
        if price <= 0: continue
        
        # 按照设定的上限，尝试重复添加同一菜品
        for _ in range(max_qty_per_item):
            for i in range(target, price - 1, -1):
                if dp[i - price] is not None:
                    new_combo = dp[i - price] + [item]
                    if dp[i] is None or len(new_combo) < len(dp[i]):
                        dp[i] = new_combo
                        
    for i in range(target, -1, -1):
        if dp[i] is not None:
            actual_sum = sum(x['price'] for x in dp[i])
            return dp[i], actual_sum
    return [], 0

# --- 3. Streamlit UI 界面 ---
st.set_page_config(page_title="金融级凑单工具-最终版", layout="wide")
st.title("⚖️ 报账菜单自动生成工具 (全功能版)")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📌 基础信息配置")
    shop_name = st.text_input("店名", "皮兄烧烤")
    address = st.text_input("用餐地址", "乐山市市中区平贤路")
    
    # 补回用餐时间输入框，默认显示当前时间
    dining_time = st.text_input("用餐时间", value=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    people_count = st.number_input("用餐人数", value=4, min_value=1)
    target_amount = st.number_input("目标报账总额 (元)", value=430)
    
    col_a, col_b = st.columns(2)
    with col_a:
        max_price_limit = st.number_input("单道菜最高限价 (元)", value=300)
    with col_b:
        user_max_qty = st.number_input("单道菜数量上限 (份)", value=10, min_value=1)

with col2:
    st.subheader("📋 粘贴原始菜单")
    raw_menu = st.text_area("请在这里粘贴菜单内容", height=320)

# --- 4. 运行与 Word 导出逻辑 ---
if st.button("🚀 开始智能凑单并生成 Word", type="primary"):
    if not raw_menu:
        st.error("❌ 请先粘贴菜单内容！")
    else:
        raw_items = parse_menu_text(raw_menu)
        extracted_items = [item for item in raw_items if item['price'] <= max_price_limit]
        
        if not extracted_items:
            st.error("❌ 菜单解析后为空，请检查格式或限价设置。")
        else:
            # 自动模式切换：低价菜单自动放宽上限
            highest_price = max([i['price'] for i in extracted_items])
            actual_max_qty = 50 if highest_price <= 15 else user_max_qty
            if highest_price <= 15:
                st.info(f"💡 检测到低价菜单（最高{highest_price}元），已自动开启【烧烤模式】，数量上限提升至 50 份。")
                
            # 执行计算
            selected_raw, total_sum = get_best_combo_bounded(extracted_items, target_amount, actual_max_qty)
            
            if not selected_raw:
                st.warning("⚠️ 无法匹配目标金额，请放宽限价或增加菜单菜品。")
            else:
                # 聚合处理：合并数量和计算小计
                counts = Counter([i['name'] for i in selected_raw])
                price_map = {i['name']: i['price'] for i in selected_raw}
                final_items = []
                for name, qty in counts.items():
                    final_items.append({
                        "name": name,
                        "qty": qty,
                        "price": price_map[name],
                        "subtotal": round(qty * price_map[name], 2)
                    })

                st.success(f"✅ 凑单成功！实测总额：{total_sum} 元")
                st.table(final_items)

                # --- Word 渲染 (含物理删行) ---
                try:
                    doc = DocxTemplate("template.docx")
                    
                    # 完整的 context 映射
                    context = {
                        'shop_name': shop_name,
                        'address': address,
                        'people': people_count,
                        'time': dining_time,  # 确保这里对应到手动输入的 dining_time
                        'total': total_sum
                    }
                    
                    # 填充 21 行固定变量
                    for i in range(1, 22):
                        if i <= len(final_items):
                            item = final_items[i-1]
                            context[f'n{i}'] = item['name']
                            context[f'q{i}'] = item['qty']
                            context[f'p{i}'] = item['price']
                            context[f't{i}'] = item['subtotal']
                        else:
                            # 没填满的行打上删除标记
                            context[f'n{i}'] = "DELETE_ROW"
                            context[f'q{i}'] = context[f'p{i}'] = context[f't{i}'] = ""

                    doc.render(context)
                    
                    # 物理删除 Word 表格中的多余空行
                    docx_obj = doc.docx
                    for table in docx_obj.tables:
                        for row in list(table.rows):
                            if "DELETE_ROW" in row.cells[0].text:
                                row._tr.getparent().remove(row._tr)
                    
                    bio = io.BytesIO()
                    doc.save(bio)
                    st.download_button(
                        label="⬇️ 点击下载生成的报账单",
                        data=bio.getvalue(),
                        file_name=f"{shop_name}_报账单.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                except Exception as e:
                    st.error(f"❌ Word 生成失败，底层报错: {e}")
