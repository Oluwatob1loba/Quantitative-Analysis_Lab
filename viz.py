
import pandas as pd
import plotly.graph_objects as go
import os

# 1. Load the setups exported by rino_engine.py
# (Make sure you've run the engine at least once so the CSV exists)
SYMBOL = 'EURUSD'   # dial
csv_path = f'reports/setups_{SYMBOL}.csv'
if not os.path.exists(csv_path):
    print(f"Error: {csv_path} not found. Run rino_engine.py first!")
    exit()

df = pd.read_csv(csv_path)

# Filter for actionable setups so the chart isn't cluttered with CONTEXT setups
# (Change to `df` if you want to see the grayed-out CONTEXT setups too)
setups = df[df['actionable'] == True].copy()

print(f"Plotting {len(setups)} actionable setups...")

fig = go.Figure()

# 2. Plot the Setups (CRT, POI, Targets, Stops)
for _, row in setups.iterrows():
    # Convert ms timestamps to datetime objects for Plotly
    t_origin = pd.to_datetime(row['origin'])
    t_avail = pd.to_datetime(row['availableAt'])
    t_future = t_avail + pd.Timedelta(days=3) # Visual extension for targets
    
    # Color logic based on direction and grade
    is_long = row['direction'] == 1
    color_main = "LimeGreen" if is_long else "Crimson"
    color_poi = "rgba(50, 205, 50, 0.2)" if is_long else "rgba(220, 20, 60, 0.2)"
    grade = row.get('grade', '?')

    # A. The Manipulation Window (The "Soup" / CRT)
    fig.add_shape(type="rect",
        x0=t_origin, y0=row['manLow'], x1=t_avail, y1=row['manHigh'],
        line=dict(color="RoyalBlue", width=1),
        fillcolor="rgba(65, 105, 225, 0.15)", name="CRT"
    )

    # B. The F-Strict POI Slice (RANGE/POI Notes)
    fig.add_shape(type="rect",
        x0=t_avail, y0=row['zoneLow'], x1=t_future, y1=row['zoneHigh'],
        line=dict(color=color_main, width=1, dash="dash"),
        fillcolor=color_poi, name=f"POI [{grade}]"
    )

    # C. The DOL Target (TS Guide)
    fig.add_trace(go.Scatter(
        x=[t_avail, t_future], y=[row['target'], row['target']],
        mode='lines', line=dict(color="Gold", width=2),
        name=f"Target ({row['targetTf']})", hoverinfo='name+y'
    ))
    
    # D. The Stop Loss
    fig.add_trace(go.Scatter(
        x=[t_avail, t_future], y=[row['stop'], row['stop']],
        mode='lines', line=dict(color="Gray", width=1, dash="dot"),
        name="Stop", hoverinfo='name+y'
    ))
    
    # E. Setup Marker (The exact candle that completed the episode)
    fig.add_trace(go.Scatter(
        x=[t_avail], y=[row['manClose']],
        mode='markers', marker=dict(symbol='triangle-up' if is_long else 'triangle-down', 
                                    size=12, color=color_main, line=dict(width=1, color='White')),
        name=f"Setup {grade}", hoverinfo='name'
    ))

# 3. Layout (TradingView Dark Mode Feel)
fig.update_layout(
    title="RINO V3 Python Lab - Eyeball Verification (Interactive)",
    xaxis_title="Time (UTC)",
    yaxis_title="Price",
    xaxis_rangeslider_visible=False, # Hides the bottom slider, just like TV
    template="plotly_dark",
    hovermode="x unified",
    showlegend=True,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)

# Save as an HTML file so you can open it in any browser and zoom/pan freely
html_path = 'reports/rino_chart.html'
fig.write_html(html_path)
print(f"Success! Open this file in your browser: {os.path.abspath(html_path)}")

# Also show it immediately if you are running in an environment that supports it
fig.show()
