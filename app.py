import streamlit as st
from docxtpl import DocxTemplate
import re
import io
import datetime

# --- 1. 智能数据清洗 ---
def parse_menu_text(text):
    items = []
    lines = text.strip().split('\n')
    for line in lines:
        line = line.strip().replace('\x07', ' ')
        if not line:
            continue
            
        nums = re.findall(r'\d+', line)
        name_part = re.sub(r'\d+', '', line).strip()

        if name_part and len(nums) >= 1:
            price = int(nums[-2]) if len(nums) >= 2 else int(nums[0])
            items.append({"name": name_part, "price": price})
            
    return items

# --- 2. 动态规划凑单算法 ---
def get_best_combo_dp(items, target):
    dp = [None] * (target + 1)
    dp[0] = [] 
    for item in items:
        price = item['price']
        name = item['name']
        for i in range(target, price - 1, -1):
            if dp[i - price] is not None and dp[i] is None:
                dp[i] = dp[i - price] + [{"name": name, "price": price}]
                
    for i in range(target, -1, -1):
        if dp[i] is not None:
            return dp[i], i
    return [], 0

# --- 3. Streamlit 交互界面 ---
st.set_page_config(page_title="金融级凑单工具-最终版", layout="wide")
st.title("⚖️ 报账菜单自动生成工具 (自动删空行版)")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📌 基础信息")
    shop_name = st.text_input("店名", "XX餐厅 (成都太古里店)")
    address = st.text_input("地址", "成都市XX区XX路XX号")
    dining_time = st.text_input("时间", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    people_count = st.number_input("人数", value=2, min_value=1)
    target_amount = st.number_input("目标报账金额", value=1068)
    # 新增约束控制
    max_price_limit = st.number_input("单道菜最高限价 (元)", value=300)

with col2:
    st.subheader("📋 粘贴菜单")
    raw_menu = st.text_area("请在这里粘贴菜单内容", height=250)

# --- 4. 运行逻辑 ---
if st.button("🚀 开始智能凑单并生成 Word", type="primary"):
    if not raw_menu:
        st.error("❌ 请输入菜单内容")
    else:
        raw_items = parse_menu_text(raw_menu)
        
        # 核心升级 1：过滤掉超过限价的菜品
        extracted_items = [item for item in raw_items if item['price'] <= max_price_limit]
        
        with st.expander("🔍 调试：查看过滤后的合格菜品池"):
            st.write(f"已剔除单价超过 {max_price_limit} 元的菜品。剩余合格菜品如下：")
            st.write(extracted_items)

        if not extracted_items:
            st.error(f"❌ 过滤失败：菜单中没有单价在 {max_price_limit} 元及以下的菜品！")
        else:
            selected_items, total_sum = get_best_combo_dp(extracted_items, target_amount)
            
            if not selected_items:
                st.warning("⚠️ 未能凑齐目标金额，请尝试放宽最高限价或调整目标总额。")
            else:
                st.success(f"✅ 计算完成！最优组合：{total_sum} 元")
                st.table(selected_items)

                # --- Word 渲染逻辑 ---
                try:
                    doc = DocxTemplate("template.docx")
                    
                    context = {
                        'shop_name': shop_name,
                        'address': address,
                        'time': dining_time,
                        'people': people_count,
                        'total': total_sum
                    }
                    
                    MAX_ROWS = 21 
                    for i in range(1, MAX_ROWS + 1):
                        if i <= len(selected_items):
                            context[f'n{i}'] = selected_items[i-1]['name']
                            context[f'p{i}'] = selected_items[i-1]['price']
                        else:
                            # 核心升级 2：给空行打上物理删除标记
                            context[f'n{i}'] = "DELETE_ROW"
                            context[f'p{i}'] = ""

                    # 替换变量
                    doc.render(context)
                    
                    # 核心升级 3：底层干预，物理切除多余的表格行
                    # 拿到 Python-docx 的原生 document 对象
                    docx_obj = doc.docx if hasattr(doc, 'docx') else doc 
                    for table in docx_obj.tables:
                        # 倒序遍历表格行，防止删除时索引错乱
                        for row in list(table.rows):
                            # 如果第一列里包含我们的删除标记
                            if "DELETE_ROW" in row.cells[0].text:
                                # 物理切除该行
                                row._tr.getparent().remove(row._tr)
                    
                    bio = io.BytesIO()
                    doc.save(bio)
                    st.download_button(
                        label="⬇️ 点击下载生成的完美报账单",
                        data=bio.getvalue(),
                        file_name=f"{shop_name}_报账单.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                except Exception as e:
                    st.error(f"❌ Word 渲染失败！底层报错: {e}")