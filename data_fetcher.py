import requests
from bs4 import BeautifulSoup
import re
import logging
import yfinance as yf
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DataFetcher:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def get_exchange_rate(self, currency_pair="USDTWD=X"):
        """
        Fetches the current exchange rate. Default is USD to TWD.
        """
        try:
            ticker = yf.Ticker(currency_pair)
            # Try to get fast info first
            price = ticker.fast_info.last_price
            if price:
                return price
            
            # Fallback to history
            hist = ticker.history(period="1d")
            if not hist.empty:
                return hist['Close'].iloc[-1]
            return 32.5 # Fallback default
        except Exception as e:
            logging.error(f"Error fetching exchange rate: {e}")
            return 32.5

    def get_historical_data(self, symbol, period="2y"):
        """
        Fetches historical price data.
        """
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period)
            return hist
        except Exception as e:
            logging.error(f"Error fetching historical data for {symbol}: {e}")
            return pd.DataFrame()

    def get_dividend_history(self, symbol):
        """
        Fetches dividend history.
        """
        try:
            ticker = yf.Ticker(symbol)
            return ticker.dividends
        except Exception as e:
            logging.error(f"Error fetching dividend history for {symbol}: {e}")
            return pd.Series(dtype=float)

    def get_dividend_info(self, symbol):
        """
        Fetches dividend information for a given symbol.
        Returns: dict {'date': str, 'yield': float}
        """
        result = {'date': 'N/A', 'yield': 0.0}
        
        # Try yfinance first
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # Get Yield
            div_yield = info.get('dividendYield')
            logging.info(f"[{symbol}] dividendYield from info: {div_yield}")
            
            if div_yield is not None:
                # yfinance returns yield as percentage (e.g. 1.36 for 1.36%), convert to decimal
                result['yield'] = div_yield / 100
            else:
                # Try to calculate from trailing annual dividend rate
                rate = info.get('trailingAnnualDividendRate')
                price = info.get('currentPrice') or info.get('regularMarketPreviousClose')
                logging.info(f"[{symbol}] Rate: {rate}, Price: {price}")
                
                if rate and price:
                    result['yield'] = rate / price
                else:
                    # Fallback: Calculate from dividend history (last 365 days)
                    try:
                        history = ticker.dividends
                        logging.info(f"[{symbol}] Dividend History Length: {len(history)}")
                        if not history.empty:
                            # Handle timezone
                            tz = history.index.tz
                            one_year_ago = pd.Timestamp.now(tz=tz) - timedelta(days=365)
                            last_year_divs = history[history.index >= one_year_ago]
                            total_div = last_year_divs.sum()
                            logging.info(f"[{symbol}] Total Div (Last Year): {total_div}")
                            
                            # Get current price
                            current_price = info.get('currentPrice') or info.get('regularMarketPreviousClose') or ticker.fast_info.last_price
                            logging.info(f"[{symbol}] Current Price for Fallback: {current_price}")
                            
                            if current_price and current_price > 0:
                                result['yield'] = total_div / current_price
                                logging.info(f"[{symbol}] Calculated yield from history: {result['yield']:.4f}")
                    except Exception as e:
                        logging.warning(f"[{symbol}] Fallback yield calculation failed: {e}")
            
            # Get Date (Ex-Dividend Date)
            ex_div_date = info.get('exDividendDate')
            if ex_div_date:
                from datetime import datetime
                result['date'] = datetime.fromtimestamp(ex_div_date).strftime('%Y/%m/%d')
                
        except Exception as e:
            logging.warning(f"yfinance dividend fetch failed for {symbol}: {e}")

        # Fallback to scraping for Date if yfinance failed or returned nothing
        if result['date'] == 'N/A' and (symbol.endswith('.TW') or symbol.endswith('.TWO')):
            url = f"https://tw.stock.yahoo.com/quote/{symbol}/dividend"
            try:
                response = requests.get(url, headers=self.headers)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    header_cell = soup.find('div', string="現金股利發放日")
                    if header_cell:
                        header_row = header_cell.find_parent('div', class_='table-header-wrapper')
                        if header_row:
                            parent = header_row.parent
                            if parent:
                                siblings = parent.find_next_siblings()
                                for sib in siblings:
                                    text = sib.get_text(strip=True)
                                    date_match = re.search(r'\d{4}/\d{2}/\d{2}', text)
                                    if date_match:
                                        result['date'] = date_match.group(0)
                                        break
            except Exception as e:
                logging.error(f"Scraping dividend info failed for {symbol}: {e}")
                
        return result

    def get_stock_price(self, symbol):
        """
        Fetches the current stock price for a given symbol (TW or US).
        Returns: float or None
        """
        # Try yfinance first for speed and consistency
        try:
            ticker = yf.Ticker(symbol)
            price = ticker.fast_info.last_price
            if price:
                return price
        except Exception as e:
            logging.warning(f"yfinance failed for {symbol}, falling back to scraping: {e}")

        url = f"https://tw.stock.yahoo.com/quote/{symbol}"
        logging.info(f"Fetching price for {symbol} from {url}")
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code != 200:
                logging.error(f"Failed to fetch {url}: Status {response.status_code}")
                return None
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Strategy 1: Look for the large price text (Fz(32px))
            price_element = soup.find('span', {'class': lambda x: x and 'Fz(32px)' in x})
            if price_element:
                price_text = price_element.text.replace(',', '')
                return float(price_text)
                
            # Strategy 2: Look for meta tags
            meta_price = soup.find('meta', {'itemprop': 'price'})
            if meta_price:
                return float(meta_price['content'])

            logging.warning(f"Could not find price element for {symbol}")
            return None
            
        except Exception as e:
            logging.error(f"Error fetching price for {symbol}: {e}")
            return None



    def get_stock_name(self, symbol):
        """
        Fetches the stock name for a given symbol.
        Prioritizes Chinese name for TW stocks.
        Returns: str or None
        """
        # 1. For TW stocks, try scraping Yahoo Finance TW first to get Chinese name
        if symbol.endswith('.TW') or symbol.endswith('.TWO'):
            url = f"https://tw.stock.yahoo.com/quote/{symbol}"
            try:
                response = requests.get(url, headers=self.headers)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Method 1: Parse <title> tag
                    # Format: "復華富時不動產 (00712) - 個股走勢 - Yahoo奇摩股市"
                    title_text = soup.title.string if soup.title else ""
                    logging.info(f"[{symbol}] Scraped Title: {title_text}")
                    
                    # Regex: Start with name, optional space, then (symbol) which might include .TW
                    # Updated to allow letters in symbol (e.g. 00981A)
                    match = re.search(r'^(.+?)\s*\(([0-9A-Z]+)(\.[A-Z]+)?\)', title_text)
                    if match:
                        name = match.group(1).strip()
                        logging.info(f"[{symbol}] Extracted Name: {name}")
                        return name
                        
                    # Method 2: Try h1 with specific class if title fails
                    h1 = soup.find('h1')
                    if h1 and "Yahoo" not in h1.text:
                        return h1.text.strip()
            except Exception as e:
                logging.error(f"Scraping name failed for {symbol}: {e}")

        # 2. Fallback to yfinance (or primary for US stocks)
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            name = info.get('shortName') or info.get('longName')
            if name:
                return name
        except Exception as e:
            logging.warning(f"yfinance name fetch failed for {symbol}: {e}")
            
        return None

if __name__ == "__main__":
    fetcher = DataFetcher()
    print(f"2330.TW Price: {fetcher.get_stock_price('2330.TW')}")
    print(f"AAPL Price: {fetcher.get_stock_price('AAPL')}")
    print(f"2330.TW Dividend: {fetcher.get_dividend_info('2330.TW')}")
    print(f"00712.TW Name: {fetcher.get_stock_name('00712.TW')}")
