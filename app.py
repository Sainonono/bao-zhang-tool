import streamlit as st
from docxtpl import DocxTemplate
import re, io, datetime, random
import pandas as pd
from collections import Counter

# --- 1. 智能数据清洗 ---
def parse_menu_text(text):
    items = []
    lines = text.strip().split('\n')
    for line in lines:
        line = line.strip().replace('\x07', ' ')
        if not line: continue
        line = line.replace('元/串', '').replace('元/份', '').replace('元', '')
        matches = re.findall(r'([^\d]+)(\d+\.?\d*)', line)
        if len(matches) > 1:
            for name_part, price_part in matches:
                name = name_part.strip()
                name = re.sub(r'^[,，。、；]+|[,，。、；]+$', '', name)
                if name and price_part:
                    items.append({"name": name, "price": float(price_part)})
        else:
            nums = re.findall(r'\d+\.?\d*', line)
            name_part = re.sub(r'\d+\.?\d*', '', line).strip()
            name_part = re.sub(r'^[,，。、；]+|[,，。、；]+$', '', name_part)
            if name_part and len(nums) >= 1:
                price = float(nums[-1])
                items.append({"name": name_part, "price": price})
    unique_items = {i['name']: i for i in items}.values()
    return list(unique_items)

# --- 2. 核心算法 ---
def get_best_combo(items, target_amount, max_qty, min_types, avoid_names=None):
    if avoid_names is None: avoid_names = []
    available_items = [i for i in items if i['name'] not in avoid_names]
    if not available_items: return [], 0
    target_int = int(round(target_amount * 100))
    min_types = min(min_types, len(available_items))
    best_overall_selected = []
    best_overall_sum = 0
    for _ in range(15):
        must_have_items = random.sample(available_items, min_types)
        current_sum = sum(int(round(i['price'] * 100)) for i in must_have_items)
        if current_sum > target_int: continue
        remaining_target = target_int - current_sum
        dp = [None] * (remaining_target + 1)
        dp[0] = []
        for item in available_items:
            price = int(round(item['price'] * 100))
            if price <= 0: continue
            for _ in range(max_qty - 1): 
                for i in range(remaining_target, price - 1, -1):
                    if dp[i - price] is not None:
                        new_combo = dp[i - price] + [item]
                        if dp[i] is None or len(new_combo) < len(dp[i]):
                            dp[i] = new_combo
        for i in range(remaining_target, -1, -1):
            if dp[i] is not None:
                total_res = must_have_items + dp[i]
                actual_sum = i + current_sum
                if actual_sum > best_overall_sum:
                    best_overall_sum = actual_sum
                    best_overall_selected = total_res
                break
    return best_overall_selected, best_overall_sum / 100.0

# --- 初始化 Session State ---
if 'menu_df' not in st.session_state:
    st.session_state.menu_df = pd.DataFrame()
if 'total_sum' not in st.session_state:
    st.session_state.total_sum = 0.0
# 【核心修复点】把默认时间放进缓存，防止被重复覆盖
if 'default_time' not in st.session_state:
    st.session_state.default_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# --- 3. Streamlit UI 界面 ---
st.set_page_config(page_title="专家干预版-报账生成器", layout="wide")
st.title("⚖️ 报账菜单自动生成器 (人机协同微调版)")

col1, col2 = st.columns([1.2, 1])

with col1:
    st.subheader("📌 基础信息与约束")
    shop_name = st.text_input("店名", "新京熹·北京涮肉(成都SKP店)")
    address = st.text_input("用餐地址", "高新区天府大道北段2001号成都SKP商场")
    
    # 这里直接调用缓存里的时间，就能随意修改了！
    dining_time = st.text_input("用餐时间", value=st.session_state.default_time)
    
    people_count = st.number_input("用餐人数", value=3, min_value=1, step=1)
    target_amount = st.number_input("目标报账总额 (元)", value=629.88, step=1.0)
    
    st.divider()
    c1, c2, c3 = st.columns(3)
    with c1: max_price_limit = st.number_input("菜品最高限价", value=299)
    with c2: user_max_qty = st.number_input("单菜数量上限", value=2, min_value=1, step=1)
    with c3: min_types = st.number_input("至少出现菜品种类", value=10, min_value=1, max_value=21, step=1)

with col2:
    st.subheader("📋 粘贴原始菜单")
    raw_menu = st.text_area("请在这里粘贴菜单内容", height=280)

# --- 4. 交互式求解逻辑 ---
st.divider()
st.subheader("🛠️ 菜单微调工作台")

col_btn1, col_btn2 = st.columns([1, 4])

with col_btn1:
    if st.button("🚀 1. 智能初算", type="primary"):
        if not raw_menu:
            st.error("请先粘贴菜单！")
        else:
            all_items = parse_menu_text(raw_menu)
            filtered_items = [i for i in all_items if i['price'] <= max_price_limit]
            
            selected_raw, total_sum = get_best_combo(filtered_items, target_amount, user_max_qty, min_types)
            if selected_raw:
                counts = Counter([i['name'] for i in selected_raw])
                price_map = {i['name']: i['price'] for i in selected_raw}
                
                df_data = []
                for name, qty in counts.items():
                    df_data.append({
                        "锁定": False, 
                        "菜品名称": name, 
                        "数量": int(qty), 
                        "单价": price_map[name], 
                        "小计": round(qty * price_map[name], 2)
                    })
                st.session_state.menu_df = pd.DataFrame(df_data)
                st.session_state.total_sum = total_sum
            else:
                st.warning("初算失败，请调整参数。")

if not st.session_state.menu_df.empty:
    st.success(f"当前总额：{st.session_state.total_sum} 元 | 目标总额：{target_amount} 元")
    st.info("💡 操作指南：在下方表格直接修改【数量】，勾选【锁定】后点击重算。程序会保留锁定的菜品，用剩余金额重新搭配其他菜。")
    
    edited_df = st.data_editor(
        st.session_state.menu_df,
        column_config={
            "锁定": st.column_config.CheckboxColumn(help="勾选后，重算时数量保持不变"),
            "菜品名称": st.column_config.TextColumn(disabled=True),
            "数量": st.column_config.NumberColumn("数量", min_value=0, step=1, format="%d"), 
            "单价": st.column_config.NumberColumn(disabled=True, format="%.2f"),
            "小计": st.column_config.NumberColumn(disabled=True, format="%.2f")
        },
        hide_index=True,
        use_container_width=True
    )

    with col_btn2:
        if st.button("🔄 2. 锁定并重算剩余金额"):
            locked_df = edited_df[edited_df["锁定"] == True].copy()
            locked_df["小计"] = locked_df["数量"] * locked_df["单价"]
            
            locked_sum = locked_df["小计"].sum()
            remaining_target = target_amount - locked_sum
            locked_names = locked_df["菜品名称"].tolist()
            
            if remaining_target < 0:
                st.error(f"❌ 锁定菜品的总额 ({locked_sum}元) 已经超过了目标总额！请调小数量。")
            else:
                all_items = parse_menu_text(raw_menu)
                filtered_items = [i for i in all_items if i['price'] <= max_price_limit]
                
                new_selected_raw, new_sum = get_best_combo(
                    filtered_items, remaining_target, user_max_qty, 
                    max(1, min_types - len(locked_df)), 
                    avoid_names=locked_names
                )
                
                counts = Counter([i['name'] for i in new_selected_raw])
                price_map = {i['name']: i['price'] for i in new_selected_raw}
                new_data = []
                for name, qty in counts.items():
                    new_data.append({
                        "锁定": False,
                        "菜品名称": name, 
                        "数量": int(qty),
                        "单价": price_map[name], 
                        "小计": round(qty * price_map[name], 2)
                    })
                new_df = pd.DataFrame(new_data)
                
                final_df = pd.concat([locked_df, new_df], ignore_index=True)
                st.session_state.menu_df = final_df
                st.session_state.total_sum = round(locked_sum + new_sum, 2)
                st.rerun()

    st.divider()
    if st.button("🖨️ 3. 确认无误，生成 Word 报账单", type="primary"):
        edited_df["数量"] = edited_df["数量"].fillna(0).astype(int)
        edited_df["单价"] = edited_df["单价"].astype(float)
        edited_df["小计"] = edited_df["数量"] * edited_df["单价"]
        final_total = edited_df["小计"].sum()
        
        try:
            doc = DocxTemplate("template.docx")
            context = {
                'shop_name': shop_name, 'address': address, 'people': people_count,
                'time': dining_time, 'total': f"{final_total:.2f}"
            }
            
            records = edited_df.to_dict('records')
            
            for i in range(1, 22):
                if i <= len(records):
                    item = records[i-1]
                    context[f'n{i}'] = item['菜品名称']
                    context[f'q{i}'] = item['数量'] 
                    context[f'p{i}'] = f"{item['单价']:.2f}"
                    context[f't{i}'] = f"{item['小计']:.2f}"
                else:
                    context[f'n{i}'] = "DELETE_ROW"
                    context[f'q{i}'] = context[f'p{i}'] = context[f't{i}'] = ""

            doc.render(context)
            docx_obj = doc.docx
            for table in docx_obj.tables:
                for row in list(table.rows):
                    if "DELETE_ROW" in row.cells[0].text:
                        row._tr.getparent().remove(row._tr)
            
            bio = io.BytesIO()
            doc.save(bio)
            st.download_button("⬇️ 下载完美报账单", bio.getvalue(), f"{shop_name}_报账单.docx")
        except Exception as e:
            st.error(f"❌ Word 渲染失败: {e}")
