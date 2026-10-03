import streamlit as st
import pandas as pd
import math
import re
from copy import deepcopy

st.set_page_config(
    page_title="Dispatch Desk – Smart Courier Optimizer",
    page_icon="🚚",
    layout="wide",
)

# -----------------------------
# Styling
# -----------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&family=Barlow+Condensed:wght@600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Barlow', sans-serif;
}
h1, h2, h3, h4 {
    font-family: 'Barlow Condensed', sans-serif;
}
.block-container {
    padding-top: 1.2rem;
    padding-bottom: 2rem;
    max-width: 1400px;
}
.hero {
    background: linear-gradient(135deg, #0d3b3e, #155e63);
    color: white;
    padding: 24px 28px;
    border-radius: 18px;
    margin-bottom: 20px;
}
.hero h1 {
    margin: 0;
    font-size: 42px;
}
.hero p {
    margin: 5px 0 0;
    opacity: .88;
    font-size: 16px;
}
.card {
    background: #f4f7f7;
    border: 1px solid #d9e4e4;
    border-radius: 14px;
    padding: 16px;
    margin-bottom: 12px;
}
.good {
    color: #087f5b;
    font-weight: 700;
}
.bad {
    color: #c92a2a;
    font-weight: 700;
}
.small {
    color: #667;
    font-size: 13px;
}
.reason {
    background: #f8faf9;
    border-left: 4px solid #138a8f;
    padding: 10px 12px;
    margin: 6px 0;
    border-radius: 6px;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Defaults from uploaded HTML
# -----------------------------
DEFAULT_PACKAGES = [
    {"id":"P1","name":"Medical supplies","weight":8,"value":900,"priority":5,"due":3,"distance":12},
    {"id":"P2","name":"Laptop order","weight":5,"value":1400,"priority":3,"due":24,"distance":25},
    {"id":"P3","name":"Furniture set","weight":30,"value":1100,"priority":2,"due":48,"distance":40},
    {"id":"P4","name":"Documents pack","weight":1,"value":300,"priority":4,"due":2,"distance":6},
    {"id":"P5","name":"Groceries crate","weight":14,"value":500,"priority":4,"due":4,"distance":9},
    {"id":"P6","name":"Printer","weight":12,"value":700,"priority":2,"due":36,"distance":18},
    {"id":"P7","name":"Legal papers","weight":1,"value":450,"priority":5,"due":3,"distance":8},
    {"id":"P8","name":"Gym equipment","weight":26,"value":950,"priority":1,"due":72,"distance":35},
    {"id":"P9","name":"Phone shipment","weight":3,"value":1600,"priority":3,"due":12,"distance":22},
    {"id":"P10","name":"Books carton","weight":15,"value":380,"priority":2,"due":48,"distance":14},
    {"id":"P11","name":"Spare parts","weight":18,"value":1250,"priority":4,"due":6,"distance":28},
    {"id":"P12","name":"Gift hamper","weight":9,"value":420,"priority":3,"due":20,"distance":16},
]
DEFAULT_CAPACITIES = [60, 45]

MODES = {
    "profit": ("Maximum profit", "Ranks parcels by delivery value only."),
    "urgent": ("Urgent delivery", "Favors tight deadlines, with value as tiebreaker."),
    "priority": ("High priority", "Favors customer priority 4–5 parcels."),
    "balanced": ("Balanced", "Blends value, priority, deadline and distance."),
}

# -----------------------------
# State
# -----------------------------
if "packages" not in st.session_state:
    st.session_state.packages = deepcopy(DEFAULT_PACKAGES)

if "capacities" not in st.session_state:
    st.session_state.capacities = DEFAULT_CAPACITIES.copy()

if "mode" not in st.session_state:
    st.session_state.mode = "balanced"

if "next_id" not in st.session_state:
    st.session_state.next_id = 13

# -----------------------------
# Core algorithm
# -----------------------------
def normalize(values):
    if not values:
        return {}
    lo = min(values)
    hi = max(values)
    if hi == lo:
        return {i: 1.0 for i in range(len(values))}
    return {i: (v - lo) / (hi - lo) for i, v in enumerate(values)}

def score_item(item, mode):
    value = float(item["value"])
    priority = float(item["priority"])
    due = max(float(item["due"]), 0.1)
    distance = float(item["distance"])

    if mode == "profit":
        return value

    if mode == "urgent":
        return (24 / due) * 100 + value / 100

    if mode == "priority":
        return priority * 100 + value / 100

    # balanced
    return (
        (value / 1600) * 45
        + (priority / 5) * 25
        + min(24 / due, 8) / 8 * 20
        + (1 / max(distance, 1)) * 10
    )

def knapsack(items, capacity, mode):
    """
    0/1 knapsack using integer kilograms.
    Returns selected item IDs.
    """
    if not items or capacity <= 0:
        return []

    # Keep only packages that fit individually.
    feasible = [x for x in items if x["weight"] <= capacity]
    if not feasible:
        return []

    n = len(feasible)
    dp = [[0.0] * (capacity + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        item = feasible[i - 1]
        wt = int(item["weight"])
        val = score_item(item, mode)

        for c in range(capacity + 1):
            dp[i][c] = dp[i - 1][c]
            if wt <= c:
                dp[i][c] = max(dp[i][c], dp[i - 1][c - wt] + val)

    selected = []
    c = capacity

    for i in range(n, 0, -1):
        if dp[i][c] != dp[i - 1][c]:
            item = feasible[i - 1]
            selected.append(item["id"])
            c -= int(item["weight"])

    selected.reverse()
    return selected

def feasibility_reason(item, max_capacity):
    # Uploaded HTML assumes a vehicle speed of 30 km/h.
    travel_hours = item["distance"] / 30
    if item["weight"] > max_capacity:
        return f"Too heavy: {item['weight']} kg exceeds the largest vehicle capacity of {max_capacity} kg."
    if travel_hours > item["due"]:
        return f"Deadline not feasible at 30 km/h: about {travel_hours:.1f} h travel for a {item['due']} h deadline."
    return None

def optimize(packages, capacities, mode):
    if not capacities:
        return {"vehicles": [], "selected": [], "rejected": [], "stats": {}}

    max_capacity = max(capacities)
    rejected = {}
    pool = []

    for item in packages:
        reason = feasibility_reason(item, max_capacity)
        if reason:
            rejected[item["id"]] = reason
        else:
            pool.append(item)

    vehicles = []
    selected_ids = []

    for vehicle_index, capacity in enumerate(capacities, start=1):
        chosen_ids = knapsack(pool, int(capacity), mode)
        chosen = [x for x in pool if x["id"] in chosen_ids]

        for x in chosen:
            selected_ids.append(x["id"])

        used_weight = sum(x["weight"] for x in chosen)
        value = sum(x["value"] for x in chosen)

        vehicles.append({
            "vehicle": f"Vehicle {vehicle_index}",
            "capacity": capacity,
            "packages": chosen,
            "used_weight": used_weight,
            "value": value,
            "utilization": (used_weight / capacity * 100) if capacity else 0,
        })

        pool = [x for x in pool if x["id"] not in chosen_ids]

    selected_set = set(selected_ids)

    # Remaining feasible packages were not selected.
    for item in packages:
        if item["id"] in rejected:
            continue
        if item["id"] not in selected_set:
            rejected[item["id"]] = "Not selected because available vehicle capacity was better used by higher-scoring packages."

    total_weight = sum(
        x["weight"] for x in packages if x["id"] in selected_set
    )
    total_value = sum(
        x["value"] for x in packages if x["id"] in selected_set
    )
    urgent_count = sum(
        1 for x in packages if x["id"] in selected_set and x["due"] <= 6
    )
    total_capacity = sum(capacities)
    utilization = total_weight / total_capacity * 100 if total_capacity else 0
    distance = sum(
        x["distance"] for x in packages if x["id"] in selected_set
    )

    return {
        "vehicles": vehicles,
        "selected": selected_set,
        "rejected": rejected,
        "stats": {
            "selected": len(selected_set),
            "total": len(packages),
            "weight": total_weight,
            "value": total_value,
            "urgent": urgent_count,
            "utilization": utilization,
            "distance": distance,
        },
    }

def route_for_vehicle(items):
    return sorted(items, key=lambda x: (x["due"], x["distance"]))

# -----------------------------
# Header
# -----------------------------
st.markdown("""
<div class="hero">
    <h1>Dispatch Desk</h1>
    <p>Pick the right parcels for each vehicle, and see why.</p>
</div>
""", unsafe_allow_html=True)

# -----------------------------
# Sidebar settings
# -----------------------------
with st.sidebar:
    st.header("⚙️ Optimization settings")

    mode = st.radio(
        "Optimization mode",
        options=list(MODES.keys()),
        index=list(MODES.keys()).index(st.session_state.mode),
        format_func=lambda x: MODES[x][0],
    )
    st.session_state.mode = mode

    st.caption(MODES[mode][1])

    st.divider()

    st.subheader("🚚 Fleet")

    vehicle_count = st.number_input(
        "Number of vehicles",
        min_value=1,
        max_value=10,
        value=len(st.session_state.capacities),
        step=1,
    )

    # Resize capacities while preserving existing values.
    caps = st.session_state.capacities[:vehicle_count]
    while len(caps) < vehicle_count:
        caps.append(40)

    for i in range(vehicle_count):
        caps[i] = st.number_input(
            f"Vehicle {i+1} capacity (kg)",
            min_value=1,
            max_value=500,
            value=int(caps[i]),
            step=1,
            key=f"cap_{i}",
        )

    st.session_state.capacities = caps

    st.divider()

    if st.button("🔄 Reset demo data", use_container_width=True):
        st.session_state.packages = deepcopy(DEFAULT_PACKAGES)
        st.session_state.capacities = DEFAULT_CAPACITIES.copy()
        st.session_state.next_id = 13
        st.rerun()

# -----------------------------
# Optimize
# -----------------------------
result = optimize(
    st.session_state.packages,
    st.session_state.capacities,
    st.session_state.mode,
)

stats = result["stats"]

# -----------------------------
# Dashboard metrics
# -----------------------------
st.subheader("📊 Dispatch overview")

c1, c2, c3, c4, c5 = st.columns(5)

c1.metric("Selected", f"{stats['selected']} / {stats['total']}")
c2.metric("Total weight", f"{stats['weight']} kg")
c3.metric("Expected value", f"₹{stats['value']:,}")
c4.metric("Urgent deliveries", stats["urgent"])
c5.metric("Fleet utilization", f"{stats['utilization']:.1f}%")

# -----------------------------
# Package management
# -----------------------------
st.subheader("📦 Packages")

with st.expander("➕ Add a new package", expanded=False):
    with st.form("add_package_form"):
        a1, a2, a3 = st.columns(3)

        with a1:
            name = st.text_input("Package name")
            weight = st.number_input("Weight (kg)", min_value=1, value=5, step=1)
            value = st.number_input("Delivery value (₹)", min_value=0, value=500, step=50)

        with a2:
            priority = st.slider("Priority", 1, 5, 3)
            due = st.number_input("Deadline (hours)", min_value=0.1, value=24.0, step=1.0)
            distance = st.number_input("Distance (km)", min_value=0.1, value=10.0, step=1.0)

        with a3:
            st.markdown("**How it works**")
            st.caption("The package is added to the optimization pool. The selected mode then decides whether it should be loaded.")

        submitted = st.form_submit_button("Add package", use_container_width=True)

        if submitted:
            clean_name = name.strip() or f"Package {st.session_state.next_id}"
            st.session_state.packages.append({
                "id": f"P{st.session_state.next_id}",
                "name": clean_name,
                "weight": int(weight),
                "value": int(value),
                "priority": int(priority),
                "due": float(due),
                "distance": float(distance),
            })
            st.session_state.next_id += 1
            st.rerun()

# Editable package table
if st.session_state.packages:
    package_df = pd.DataFrame(st.session_state.packages)

    edited = st.data_editor(
        package_df,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        column_config={
            "id": st.column_config.TextColumn("ID", disabled=True),
            "name": st.column_config.TextColumn("Package"),
            "weight": st.column_config.NumberColumn("Weight (kg)", min_value=1),
            "value": st.column_config.NumberColumn("Value (₹)", min_value=0),
            "priority": st.column_config.NumberColumn("Priority", min_value=1, max_value=5),
            "due": st.column_config.NumberColumn("Deadline (h)", min_value=0.1),
            "distance": st.column_config.NumberColumn("Distance (km)", min_value=0.1),
        },
        key="package_editor",
    )

    # Keep session state synchronized with edited table.
    new_packages = edited.to_dict("records")
    for item in new_packages:
        item["weight"] = int(item["weight"])
        item["value"] = int(item["value"])
        item["priority"] = max(1, min(5, int(item["priority"])))
        item["due"] = float(item["due"])
        item["distance"] = float(item["distance"])

    st.session_state.packages = new_packages

    if st.button("🗑️ Remove last package", type="secondary"):
        if st.session_state.packages:
            st.session_state.packages.pop()
            st.rerun()

# Recalculate after possible editor changes.
result = optimize(
    st.session_state.packages,
    st.session_state.capacities,
    st.session_state.mode,
)
stats = result["stats"]

# -----------------------------
# Vehicle assignment
# -----------------------------
st.subheader("🚚 Vehicle assignments")

if not result["vehicles"]:
    st.info("No vehicles configured.")
else:
    cols = st.columns(min(3, len(result["vehicles"])))

    for idx, vehicle in enumerate(result["vehicles"]):
        with cols[idx % len(cols)]:
            st.markdown(f"### {vehicle['vehicle']}")
            st.caption(
                f"Capacity: {vehicle['capacity']} kg · "
                f"Used: {vehicle['used_weight']} kg · "
                f"Utilization: {vehicle['utilization']:.1f}%"
            )

            if vehicle["packages"]:
                for item in vehicle["packages"]:
                    st.markdown(
                        f"**{item['id']} — {item['name']}**  \n"
                        f"{item['weight']} kg · ₹{item['value']:,} · "
                        f"P{item['priority']} · due {item['due']} h"
                    )
            else:
                st.info("No packages selected.")

# -----------------------------
# What-if simulator
# -----------------------------
st.subheader("🧪 What-if simulator")

with st.expander("Change a vehicle capacity and see the result", expanded=False):
    vehicle_number = st.number_input(
        "Vehicle number",
        min_value=1,
        max_value=len(st.session_state.capacities),
        value=1,
        step=1,
        key="what_if_vehicle",
    )

    current_cap = st.session_state.capacities[vehicle_number - 1]
    what_if_cap = st.slider(
        "What-if capacity (kg)",
        min_value=1,
        max_value=500,
        value=int(current_cap),
        step=1,
    )

    what_if_caps = st.session_state.capacities.copy()
    what_if_caps[vehicle_number - 1] = what_if_cap

    what_if = optimize(
        st.session_state.packages,
        what_if_caps,
        st.session_state.mode,
    )

    w1, w2, w3 = st.columns(3)
    w1.metric("Packages selected", what_if["stats"]["selected"])
    w2.metric("Expected value", f"₹{what_if['stats']['value']:,}")
    w3.metric("Fleet utilization", f"{what_if['stats']['utilization']:.1f}%")

    current_value = stats["value"]
    delta = what_if["stats"]["value"] - current_value

    if delta > 0:
        st.success(f"Increasing/changing capacity produces ₹{delta:,} more expected delivery value.")
    elif delta < 0:
        st.warning(f"This what-if configuration produces ₹{abs(delta):,} less expected delivery value.")
    else:
        st.info("This capacity change does not change the current expected delivery value.")

# -----------------------------
# Selected / rejected explanations
# -----------------------------
st.subheader("💡 Why these packages?")

left, right = st.columns(2)

with left:
    st.markdown("### ✅ Selected")
    selected_items = [
        x for x in st.session_state.packages
        if x["id"] in result["selected"]
    ]

    if not selected_items:
        st.info("No packages selected.")
    else:
        for item in selected_items:
            if st.session_state.mode == "profit":
                explanation = f"High delivery value: ₹{item['value']:,}."
            elif st.session_state.mode == "urgent":
                explanation = f"Deadline is {item['due']} h, so urgency increases its score."
            elif st.session_state.mode == "priority":
                explanation = f"Customer priority is {item['priority']}/5."
            else:
                explanation = (
                    f"Balanced score from value ₹{item['value']:,}, "
                    f"priority {item['priority']}/5, deadline {item['due']} h "
                    f"and distance {item['distance']} km."
                )

            st.markdown(
                f'<div class="reason"><b>{item["id"]} — {item["name"]}</b><br>{explanation}</div>',
                unsafe_allow_html=True,
            )

with right:
    st.markdown("### ❌ Rejected / not loaded")

    if not result["rejected"]:
        st.info("No rejected packages.")
    else:
        item_lookup = {x["id"]: x for x in st.session_state.packages}

        for pid, reason in result["rejected"].items():
            item = item_lookup[pid]
            st.markdown(
                f'<div class="reason"><b>{item["id"]} — {item["name"]}</b><br>{reason}</div>',
                unsafe_allow_html=True,
            )

# -----------------------------
# Delivery order
# -----------------------------
st.subheader("🗺️ Delivery order")

for vehicle in result["vehicles"]:
    st.markdown(f"### {vehicle['vehicle']}")

    ordered = route_for_vehicle(vehicle["packages"])

    if not ordered:
        st.info("No route because this vehicle has no assigned packages.")
        continue

    route_df = pd.DataFrame([
        {
            "Stop": i,
            "Package": x["id"],
            "Name": x["name"],
            "Deadline (h)": x["due"],
            "Distance (km)": x["distance"],
            "Priority": x["priority"],
        }
        for i, x in enumerate(ordered, start=1)
    ])

    st.dataframe(route_df, hide_index=True, use_container_width=True)

# -----------------------------
# Planner assistant
# -----------------------------
st.subheader("🤖 Planner assistant")

question = st.text_input(
    "Ask about the current dispatch plan",
    placeholder="Example: Why was P3 rejected?",
)

quick = st.columns(4)
quick_questions = [
    "Why was P3 rejected?",
    "Which deliveries are urgent?",
    "What is fleet utilization?",
    "What is the expected value?",
]

for col, q in zip(quick, quick_questions):
    if col.button(q, use_container_width=True):
        question = q

def assistant_answer(q):
    ql = q.lower().strip()
    item_lookup = {x["id"].lower(): x for x in st.session_state.packages}

    # Package-specific rejection
    match = re.search(r"\bp(\d+)\b", ql)
    if match:
        pid = "p" + match.group(1)
        if pid in item_lookup:
            item = item_lookup[pid]
            if item["id"] in result["rejected"]:
                return f"**{item['id']} — {item['name']}** was not loaded because: {result['rejected'][item['id']]}"
            if item["id"] in result["selected"]:
                return f"**{item['id']} — {item['name']}** was selected. It fits the available capacity and scores well under the **{MODES[st.session_state.mode][0]}** mode."
            return f"I found {item['id']} — {item['name']}, but it is not currently in the selected set."

    if "urgent" in ql:
        urgent = sorted(st.session_state.packages, key=lambda x: x["due"])
        urgent = urgent[:5]
        return "Urgent packages by deadline: " + ", ".join(
            f"{x['id']} ({x['due']}h)" for x in urgent
        )

    if "utilization" in ql or "capacity" in ql:
        return (
            f"Fleet utilization is **{stats['utilization']:.1f}%**. "
            f"The fleet is carrying **{stats['weight']} kg** across "
            f"{sum(st.session_state.capacities)} kg total capacity."
        )

    if "profit" in ql or "value" in ql or "revenue" in ql:
        return (
            f"The current plan has an expected delivery value of "
            f"**₹{stats['value']:,}** from {stats['selected']} selected packages."
        )

    if "route" in ql or "order" in ql:
        lines = []
        for v in result["vehicles"]:
            ordered = route_for_vehicle(v["packages"])
            if ordered:
                lines.append(
                    f"{v['vehicle']}: " +
                    " → ".join(x["id"] for x in ordered)
                )
        return "\n\n".join(lines) if lines else "No delivery route is currently available."

    if "mode" in ql:
        return (
            f"Current mode: **{MODES[st.session_state.mode][0]}** — "
            f"{MODES[st.session_state.mode][1]}"
        )

    return (
        "I can explain package selection, rejection reasons, urgent deliveries, "
        "fleet utilization, expected value, or delivery order."
    )

if question:
    st.markdown(
        f'<div class="card"><b>Planner:</b><br>{assistant_answer(question)}</div>',
        unsafe_allow_html=True,
    )

# -----------------------------
# Footer
# -----------------------------
st.divider()
st.caption(
    "Dispatch Desk – Smart Courier Optimizer | "
    "0/1 knapsack-based package selection with explainable dispatch planning."
)
