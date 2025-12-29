import streamlit as st
import pandas as pd
from data_fetcher import DataFetcher
from portfolio_calculator import PortfolioCalculator

st.set_page_config(page_title="活水計畫 - 智能投資組合", layout="wide")

# --- API Key Gatekeeper ---
if 'gemini_api_key' not in st.session_state:
    st.session_state.gemini_api_key = ""

if not st.session_state.gemini_api_key:
    st.title("🔐 系統啟動驗證")
    st.markdown("請輸入您的 **Gemini API Key** 以啟動智能投資組合服務。")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        api_input = st.text_input("Gemini API Key", type="password", label_visibility="collapsed", placeholder="Enter your API Key here...")
    with col2:
        confirm_btn = st.button("啟動服務", type="primary")
        
    if confirm_btn:
        if api_input.strip():
            st.session_state.gemini_api_key = api_input.strip()
            st.rerun()
        else:
            st.error("⚠️ 請輸入有效的 API Key")
            
    st.divider()
    st.caption("本服務需要 Gemini API Key 進行驗證與潛在的 AI 分析功能。")
    st.stop()
# --------------------------

st.title("🌊 活水計畫 (Living Water Project)")
st.subheader("智能投資組合配置系統")

# Sidebar
st.sidebar.header("投資設定")

# Investment Mode Selection
mode_selection = st.sidebar.radio("投資模式", ["單筆投入", "定期定額"])

if mode_selection == "單筆投入":
    investment_mode = "lump_sum"
    total_capital = st.number_input("總投資金額 (TWD)", min_value=10000, value=1000000, step=10000)
    monthly_income_goal = st.number_input("希望月收入金額 (TWD)", min_value=1000, value=5000, step=1000)
else:
    investment_mode = "dca"
    monthly_investment = st.number_input("每月定期定額 (TWD)", min_value=1000, value=10000, step=1000)
    dca_years = st.slider("投資年限 (年)", 1, 30, 10)
    # For DCA, we calculate a hypothetical portfolio based on 1 year of contributions to show allocation
    total_capital = monthly_investment * 12 
    monthly_income_goal = 0 # Not relevant for input, but output

st.sidebar.divider()

st.sidebar.header("資產配置比重 (%)")
w_stock = st.sidebar.number_input("證券比重", 0, 100, 50, step=5)
w_etf = st.sidebar.number_input("ETF比重", 0, 100, 30, step=5)
w_bond = st.sidebar.number_input("債券比重", 0, 100, 20, step=5)

total_weight = w_stock + w_etf + w_bond
if total_weight != 100:
    st.sidebar.error(f"目前總和: {total_weight}%，請調整至 100%")
    
st.sidebar.divider()

# Custom Products
st.sidebar.header("自訂商品 (選填)")
with st.sidebar.expander("新增自訂商品"):
    custom_symbol = st.text_input("股票代號 (例如 2330.TW)", value="")
    custom_weight = st.number_input("配置權重 (%)", 0, 100, 0, step=5)
    
    if 'custom_allocations' not in st.session_state:
        st.session_state['custom_allocations'] = []
        
    if st.button("加入清單"):
        if custom_symbol and custom_weight > 0:
            st.session_state['custom_allocations'].append({'symbol': custom_symbol, 'weight': custom_weight/100})
            st.success(f"已加入 {custom_symbol}")
        else:
            st.error("請輸入代號與權重")
            
    # Display current custom list
    if st.session_state['custom_allocations']:
        st.write("已選商品:")
        new_allocs = []
        for i, item in enumerate(st.session_state['custom_allocations']):
            col_c1, col_c2 = st.columns([3, 1])
            col_c1.text(f"{item['symbol']} ({item['weight']*100:.0f}%)")
            if col_c2.button("刪", key=f"del_{i}"):
                pass # Will be removed in next rerun logic if we rebuild list, simpler to just clear all
            else:
                new_allocs.append(item)
        st.session_state['custom_allocations'] = new_allocs
        
        if st.button("清空自訂清單"):
            st.session_state['custom_allocations'] = []
            st.rerun()

st.sidebar.divider()

if investment_mode == "lump_sum":
    st.info(f"目標年收入: {monthly_income_goal * 12:,.0f} TWD")
    st.info(f"目標年殖利率: {(monthly_income_goal * 12 / total_capital) * 100:.2f}%")
else:
    st.info(f"預計年投入: {monthly_investment * 12:,.0f} TWD")

if st.button("生成投資組合", type="primary", disabled=(total_weight != 100)):
    with st.spinner("正在查詢市場數據並計算多重方案..."):
        fetcher = DataFetcher()
        calculator = PortfolioCalculator()
        user_weights = {'Stock': w_stock/100, 'ETF': w_etf/100, 'Bond': w_bond/100}
        custom_allocs = st.session_state.get('custom_allocations', [])
        
        scenarios = calculator.generate_scenarios(total_capital, monthly_income_goal, fetcher, user_weights, custom_allocs)
        st.session_state['scenarios'] = scenarios
        st.session_state['investment_mode'] = investment_mode
        if investment_mode == "dca":
            st.session_state['dca_params'] = {'monthly': monthly_investment, 'years': dca_years}
            
        st.success("計算完成！")

def display_portfolio_result(portfolio_data, title, mode="lump_sum", dca_params=None):
    portfolio, required_yield, usd_twd, history_series = portfolio_data
    
    st.header(title)
    st.info(f"當前匯率: 1 USD = {usd_twd:.2f} TWD")
    
    # Summary Metrics
    total_cost = sum(item['cost_twd'] for item in portfolio)
    total_income = sum(item['est_annual_income'] for item in portfolio)
    actual_yield = (total_income / total_cost) * 100 if total_cost > 0 else 0
    
    if mode == "lump_sum":
        col1, col2, col3 = st.columns(3)
        col1.metric("總投資成本", f"{total_cost:,.0f} TWD")
        col2.metric("預估年收入", f"{total_income:,.0f} TWD")
        col3.metric("預估殖利率", f"{actual_yield:.2f}%")
    else:
        # DCA Projection
        st.subheader("定期定額資產預測")
        monthly = dca_params['monthly']
        years = dca_params['years']
        
        # Calculate Projection
        calculator = PortfolioCalculator()
        proj_df = calculator.calculate_dca_projection(monthly, years, actual_yield)
        
        if not proj_df.empty:
            final_fv = proj_df.iloc[-1]['Asset Value']
            final_cost = proj_df.iloc[-1]['Total Cost']
            final_income = proj_df.iloc[-1]['Passive Income (Yearly)'] / 12
            
            c1, c2, c3 = st.columns(3)
            c1.metric(f"{years}年後總資產", f"{final_fv:,.0f} TWD", delta=f"+{final_fv-final_cost:,.0f}")
            c2.metric("總投入成本", f"{final_cost:,.0f} TWD")
            c3.metric("預估未來月被動收入", f"{final_income:,.0f} TWD")
            
            st.line_chart(proj_df.set_index('Year')[['Total Cost', 'Asset Value']])
    
    # Portfolio Table
    st.subheader("建議配置 (基於當前資金)")
    df = pd.DataFrame(portfolio)
    
    if not df.empty:
        # Format columns
        st.dataframe(
            df,
            column_config={
                "symbol": "代碼",
                "name": "名稱",
                "type": "類型",
                "price": st.column_config.NumberColumn("市價 (原幣)", format="%.2f"),
                "quantity": st.column_config.NumberColumn("建議股數", format="%d"),
                "cost_twd": st.column_config.NumberColumn("預估成本 (TWD)", format="$%d"),
                "yield_rate": st.column_config.NumberColumn("殖利率 (%)", format="%.2f%%"),
                "est_annual_income": st.column_config.NumberColumn("預估年收 (TWD)", format="$%d"),
                "dividend_date": "最近配息日",
                "pros": "優點",
                "cons": "缺點",
                "fill_dividend_2y": "近2年填息(次)",
                "avg_fill_days": "平均填息天數"
            },
            column_order=["symbol", "name", "type", "price", "quantity", "cost_twd", "yield_rate", "est_annual_income", "dividend_date", "fill_dividend_2y", "avg_fill_days", "pros", "cons"],
            hide_index=True,
            use_container_width=True
        )
        
        # Charts
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.subheader("資產配置 (圓餅圖)")
            import plotly.express as px
            fig = px.pie(df, values='cost_twd', names='name', title='投資組合配置')
            st.plotly_chart(fig, use_container_width=True)
            
        with col_chart2:
            st.subheader("過去6個月資產走勢 (回測)")
            if not history_series.empty:
                st.line_chart(history_series)
            else:
                st.write("無足夠歷史數據可顯示走勢圖")
    else:
        st.warning("此配置下無合適的投資標的。")

# Main content
if 'scenarios' in st.session_state:
    scenarios = st.session_state['scenarios']
    mode = st.session_state.get('investment_mode', 'lump_sum')
    dca_params = st.session_state.get('dca_params', None)
    
    tab1, tab2, tab3 = st.tabs(["自訂組合 (Custom)", "保守型 (Conservative)", "積極型 (Aggressive)"])
    
    with tab1:
        display_portfolio_result(scenarios['Custom'], "自訂組合方案", mode, dca_params)
    with tab2:
        display_portfolio_result(scenarios['Conservative'], "保守型方案 (高債券/ETF)", mode, dca_params)
    with tab3:
        display_portfolio_result(scenarios['Aggressive'], "積極型方案 (高股票)", mode, dca_params)

else:
    st.info("請在左側輸入您的資金規劃與比重，並點擊「生成投資組合」")
