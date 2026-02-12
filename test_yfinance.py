import yfinance as yf

ticker = yf.Ticker('AAPL')
print('Options expiration dates:')
print(ticker.options)
print()

if ticker.options:
    print(f'Found {len(ticker.options)} expiration dates')
    print(f'First expiry: {ticker.options[0]}')
    
    chain = ticker.option_chain(ticker.options[0])
    print(f'Calls: {len(chain.calls)}')
    print(f'Puts: {len(chain.puts)}')
    
    if len(chain.calls) > 0:
        print('\nSample call data:')
        print(chain.calls[['strike', 'bid', 'ask', 'volume', 'openInterest']].head())
else:
    print('No options found!')
