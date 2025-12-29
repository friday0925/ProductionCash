import pandas as pd
import numpy as np
from datetime import timedelta

class PortfolioCalculator:
    def __init__(self):
        # Candidate pool (Simplified for MVP)
        self.candidates = [
            {'symbol': '2330.TW', 'name': '台積電', 'type': 'Stock', 'market': 'TW'},
            {'symbol': '0050.TW', 'name': '元大台灣50', 'type': 'ETF', 'market': 'TW'},
            {'symbol': '0056.TW', 'name': '元大高股息', 'type': 'ETF', 'market': 'TW'},
            {'symbol': 'AAPL', 'name': 'Apple Inc.', 'type': 'Stock', 'market': 'US'},
            {'symbol': 'VOO', 'name': 'Vanguard S&P 500 ETF', 'type': 'ETF', 'market': 'US'},
            {'symbol': '00679B.TW', 'name': '元大美債20年', 'type': 'Bond', 'market': 'TW'},
            {'symbol': 'BND', 'name': 'Vanguard Total Bond Market', 'type': 'Bond', 'market': 'US'},
        ]
        
        self.pros_cons_db = {
            '2330.TW': {'pros': '全球晶圓代工龍頭，技術領先', 'cons': '受地緣政治風險影響較大'},
            '0050.TW': {'pros': '追蹤台股前50大市值公司，跟隨大盤成長', 'cons': '受單一產業(半導體)權重影響大'},
            '0056.TW': {'pros': '高股息殖利率，現金流穩定', 'cons': '成長性可能不如市值型ETF'},
            'AAPL': {'pros': '強大的品牌護城河與生態系', 'cons': '硬體銷售成長趨緩'},
            'VOO': {'pros': '分散投資美國500大企業，費用率極低', 'cons': '匯率風險'},
            '00679B.TW': {'pros': '投資美國長天期公債，避險效果佳', 'cons': '受聯準會利率政策影響大'},
            'BND': {'pros': '廣泛投資美國投資級債券，波動低', 'cons': '收益率相對股票較低'},
        }

    def get_pros_cons(self, symbol):
        return self.pros_cons_db.get(symbol, {'pros': 'N/A', 'cons': 'N/A'})

    def analyze_fill_dividend(self, symbol, history, dividends):
        """
        Analyzes fill dividend status for the last 2 years.
        Returns: {'filled_count': int, 'total_count': int, 'avg_days': float}
        """
        if history.empty or dividends.empty:
            return {'filled_count': 0, 'total_count': 0, 'avg_days': 0}

        # Filter dividends for last 2 years
        cutoff_date = pd.Timestamp.now(tz=dividends.index.tz) - timedelta(days=730)
        recent_dividends = dividends[dividends.index >= cutoff_date]
        
        if recent_dividends.empty:
            return {'filled_count': 0, 'total_count': 0, 'avg_days': 0}

        filled_count = 0
        total_days = 0
        
        for date, amount in recent_dividends.items():
            # Find the ex-dividend date index in history
            # yfinance dividend dates are usually ex-dates
            try:
                # Convert to timezone naive for comparison if needed, or ensure match
                # history index is usually tz-aware if downloaded that way.
                # Let's try to find the closest trading day at or after ex-date
                ex_date_idx = history.index.searchsorted(date)
                if ex_date_idx >= len(history):
                    continue
                    
                ex_date_price = history.iloc[ex_date_idx]['Close']
                # Pre-dividend price reference (approximate as Close + Dividend or Prev Close)
                # Strictly speaking, fill dividend means price returns to pre-ex-dividend close.
                # Pre-ex-dividend close = Open on ex-day? No, Close of prev day.
                
                if ex_date_idx > 0:
                    pre_close = history.iloc[ex_date_idx - 1]['Close']
                else:
                    pre_close = ex_date_price + amount # Approximation

                # Check if price recovered to pre_close
                future_prices = history.iloc[ex_date_idx:]['High'] # Use High to check if it touched the price
                
                days_to_fill = 0
                filled = False
                
                for i, price in enumerate(future_prices):
                    if price >= pre_close:
                        days_to_fill = i
                        filled = True
                        break
                
                if filled:
                    filled_count += 1
                    total_days += days_to_fill
                    
            except Exception as e:
                continue

        avg_days = total_days / filled_count if filled_count > 0 else 0
        return {
            'filled_count': filled_count, 
            'total_count': len(recent_dividends), 
            'avg_days': avg_days
        }

    def calculate_portfolio(self, total_capital, monthly_income_goal, fetcher, weights, custom_allocations=[]):
        """
        Calculates a proposed portfolio allocation based on weights.
        weights: dict {'Stock': float, 'ETF': float, 'Bond': float} (sum to 1.0)
        custom_allocations: list of dict {'symbol': str, 'weight': float} (weight is 0.0-1.0)
        """
        annual_income_goal = monthly_income_goal * 12
        required_yield = (annual_income_goal / total_capital) * 100 if total_capital > 0 else 0
        
        portfolio = []
        
        # Get Exchange Rate
        usd_twd = fetcher.get_exchange_rate()
        
        # 1. Process Custom Allocations first
        remaining_capital = total_capital
        
        for custom in custom_allocations:
            symbol = custom['symbol']
            weight = custom['weight']
            
            # Validate symbol exists/is fetchable (simple check)
            price = fetcher.get_stock_price(symbol)
            if not price:
                logging.warning(f"Could not fetch price for custom symbol: {symbol}")
                continue
                
            alloc_capital = total_capital * weight
            remaining_capital -= alloc_capital
            
            div_info = fetcher.get_dividend_info(symbol)
            history = fetcher.get_historical_data(symbol, period="2y")
            dividends = fetcher.get_dividend_history(symbol)
            fill_stats = self.analyze_fill_dividend(symbol, history, dividends)
            pros_cons = self.get_pros_cons(symbol)
            
            # Fetch Name
            stock_name = fetcher.get_stock_name(symbol)
            display_name = f"{stock_name} ({symbol})" if stock_name else f"{symbol} (自訂)"
            
            price_twd = price
            # Guess market based on symbol format or previous knowledge
            # Simple heuristic: .TW or .TWO is TW, else US
            is_us = not (symbol.endswith('.TW') or symbol.endswith('.TWO'))
            if is_us:
                price_twd = price * usd_twd
            
            quantity = int(alloc_capital / price_twd) if price_twd > 0 else 0
            cost = quantity * price_twd
            
            yield_rate = div_info.get('yield', 0.0)
            if yield_rate is None: yield_rate = 0.0
            
            est_annual_income = cost * yield_rate
            
            portfolio.append({
                'symbol': symbol,
                'name': display_name,
                'type': 'Custom',
                'price': price,
                'price_twd': price_twd,
                'quantity': quantity,
                'cost_twd': cost,
                'est_annual_income': est_annual_income,
                'yield_rate': yield_rate * 100,
                'dividend_date': div_info.get('date', 'N/A'),
                'pros': pros_cons['pros'],
                'cons': pros_cons['cons'],
                'fill_dividend_2y': f"{fill_stats['filled_count']}/{fill_stats['total_count']}",
                'avg_fill_days': f"{fill_stats['avg_days']:.1f} 天"
            })

        # 2. Allocate Remaining Capital to Categories
        if remaining_capital > 0:
            # Filter candidates by type
            stocks = [c for c in self.candidates if c['type'] == 'Stock']
            etfs = [c for c in self.candidates if c['type'] == 'ETF']
            bonds = [c for c in self.candidates if c['type'] == 'Bond']
            
            # Allocate capital to categories based on weights (relative to remaining)
            # Weights sum to 1.0 (100%). We apply these % to the *Remaining Capital*.
            capital_stock = remaining_capital * weights.get('Stock', 0)
            capital_etf = remaining_capital * weights.get('ETF', 0)
            capital_bond = remaining_capital * weights.get('Bond', 0)
            
            # For backtesting (only for auto-allocated parts + custom? 
            # Ideally backtest everything. Let's rebuild history for ALL items at the end)
            
            def process_category(candidates, available_capital):
                if not candidates or available_capital <= 0:
                    return
                
                allocation_per_asset = available_capital / len(candidates)
                
                for candidate in candidates:
                    symbol = candidate['symbol']
                    price = fetcher.get_stock_price(symbol)
                    div_info = fetcher.get_dividend_info(symbol)
                    
                    history = fetcher.get_historical_data(symbol, period="2y")
                    dividends = fetcher.get_dividend_history(symbol)
                    fill_stats = self.analyze_fill_dividend(symbol, history, dividends)
                    pros_cons = self.get_pros_cons(symbol)
                    
                    if price:
                        price_twd = price
                        if candidate['market'] == 'US':
                            price_twd = price * usd_twd
                        
                        quantity = int(allocation_per_asset / price_twd)
                        cost = quantity * price_twd
                        
                        yield_rate = div_info.get('yield', 0.0)
                        if yield_rate is None: yield_rate = 0.0
                        
                        est_annual_income = cost * yield_rate
                        
                        portfolio.append({
                            'symbol': symbol,
                            'name': candidate['name'],
                            'type': candidate['type'],
                            'price': price,
                            'price_twd': price_twd,
                            'quantity': quantity,
                            'cost_twd': cost,
                            'est_annual_income': est_annual_income,
                            'yield_rate': yield_rate * 100,
                            'dividend_date': div_info.get('date', 'N/A'),
                            'pros': pros_cons['pros'],
                            'cons': pros_cons['cons'],
                            'fill_dividend_2y': f"{fill_stats['filled_count']}/{fill_stats['total_count']}",
                            'avg_fill_days': f"{fill_stats['avg_days']:.1f} 天"
                        })

            process_category(stocks, capital_stock)
            process_category(etfs, capital_etf)
            process_category(bonds, capital_bond)

        # 3. Generate Total History (Backtest) for the entire portfolio
        portfolio_history = pd.DataFrame()
        for item in portfolio:
            symbol = item['symbol']
            quantity = item['quantity']
            
            # We need to re-fetch history if not cached, but for now let's just fetch again or optimize later
            # To save time, we could have stored history in the item dict, but it's heavy.
            # Let's just fetch 6mo history here.
            history = fetcher.get_historical_data(symbol, period="6mo")
            
            if not history.empty:
                recent_history = history['Close'].copy()
                
                # Determine market for currency conversion
                is_us = not (symbol.endswith('.TW') or symbol.endswith('.TWO'))
                if is_us:
                    recent_history = recent_history * usd_twd * quantity
                else:
                    recent_history = recent_history * quantity
                    
                if portfolio_history.empty:
                    portfolio_history = pd.DataFrame(recent_history).rename(columns={'Close': symbol})
                else:
                    # Check if symbol already exists in columns to avoid overlap error
                    if symbol not in portfolio_history.columns:
                        portfolio_history = portfolio_history.join(pd.DataFrame(recent_history).rename(columns={'Close': symbol}), how='outer')

        # Calculate Total Portfolio Value History
        total_history = pd.Series()
        if not portfolio_history.empty:
            portfolio_history['Total Value'] = portfolio_history.sum(axis=1)
            total_history = portfolio_history['Total Value'].ffill().bfill()
                
        return portfolio, required_yield, usd_twd, total_history

    def calculate_dca_projection(self, monthly_amount, years, portfolio_yield_percent):
        """
        Calculates future value for DCA.
        Assumes:
        - Monthly investment at beginning of month.
        - Reinvested dividends? Simplified: Total Return = Yield + Growth.
        - Let's assume a conservative Capital Growth rate of 3% + Yield.
        """
        months = years * 12
        annual_growth_rate = 0.03 # 3% capital appreciation assumption
        total_annual_return = (portfolio_yield_percent / 100) + annual_growth_rate
        monthly_return = total_annual_return / 12
        
        future_value = 0
        total_cost = 0
        
        # FV = P * ((1+r)^n - 1)/r * (1+r)
        if monthly_return > 0:
            future_value = monthly_amount * (((1 + monthly_return) ** months - 1) / monthly_return) * (1 + monthly_return)
        else:
            future_value = monthly_amount * months
            
        total_cost = monthly_amount * months
        
        # Generate chart data (Yearly)
        data = []
        current_fv = 0
        current_cost = 0
        for m in range(1, months + 1):
            current_cost += monthly_amount
            current_fv = (current_fv + monthly_amount) * (1 + monthly_return)
            
            if m % 12 == 0:
                year = m // 12
                data.append({
                    'Year': year,
                    'Total Cost': current_cost,
                    'Asset Value': current_fv,
                    'Passive Income (Yearly)': current_fv * (portfolio_yield_percent / 100)
                })
                
        return pd.DataFrame(data)

    def generate_scenarios(self, total_capital, monthly_income_goal, fetcher, user_weights, custom_allocations=[]):
        """
        Generates 3 scenarios: Custom, Conservative, Aggressive.
        """
        # 1. Custom (Includes User's Custom Products)
        custom_port = self.calculate_portfolio(total_capital, monthly_income_goal, fetcher, user_weights, custom_allocations)
        
        # 2. Conservative (Stock 20%, ETF 40%, Bond 40%) - No custom products for standard scenarios
        conservative_weights = {'Stock': 0.2, 'ETF': 0.4, 'Bond': 0.4}
        conservative_port = self.calculate_portfolio(total_capital, monthly_income_goal, fetcher, conservative_weights, [])
        
        # 3. Aggressive (Stock 60%, ETF 40%, Bond 0%) - No custom products for standard scenarios
        aggressive_weights = {'Stock': 0.6, 'ETF': 0.4, 'Bond': 0.0}
        aggressive_port = self.calculate_portfolio(total_capital, monthly_income_goal, fetcher, aggressive_weights, [])
        
        return {
            'Custom': custom_port,
            'Conservative': conservative_port,
            'Aggressive': aggressive_port
        }
