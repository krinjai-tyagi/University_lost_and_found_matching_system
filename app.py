import streamlit as st

from auth import get_user, login_user, register_user
from claims import (create_claim, get_claims_by_claimant, get_match_id,
                    get_pending_claims_for_finder, question_for, review_claim)
from db_helpers import (CATEGORIES, LOCATIONS, add_item, add_sample_data,
                        category_label, get_items, init_db, save_matches)
from embeddings import AVAILABLE as SBERT_AVAILABLE
from image_matching import AVAILABLE as PHOTO_AVAILABLE
from image_matching import full_path, save_uploaded_image
from matching_engine import detect_duplicates, find_matches
from reputation import (FALSE_CLAIM_PENALTY, FINDER_REWARD, LOW_REPUTATION_LIMIT,
                        get_reputation, get_reputation_log, trust_level)

st.set_page_config(page_title="FindrAlgo", page_icon="🔍")
init_db()

st.title("🔍 FindrAlgo")
st.caption("Smart Lost and Found Matching System")


# ====================== Login / Sign up ======================
def show_login_page():
    tab_login, tab_signup = st.tabs(["Login", "Sign up"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            login_clicked = st.form_submit_button("Login")
        if login_clicked:
            user = login_user(email, password)
            if user:
                st.session_state["user"] = user
                st.rerun()
            else:
                st.error("Wrong email or password.")

    with tab_signup:
        with st.form("signup_form"):
            name = st.text_input("Full name")
            email2 = st.text_input("Email", key="signup_email")
            password2 = st.text_input("Password (min 6 characters)", type="password", key="signup_pw")
            signup_clicked = st.form_submit_button("Create account")
        if signup_clicked:
            ok, result = register_user(name, email2, password2)
            if ok:
                st.success("Account created! Now log in from the Login tab.")
            else:
                st.error(result)


def show_photo(image_path, caption, width=160):
    """Shows a saved photo if it exists."""
    if image_path and full_path(image_path).exists():
        st.image(str(full_path(image_path)), caption=caption, width=width)


user = st.session_state.get("user")
if user is None:
    show_login_page()
    st.stop()

user_id = user["user_id"]


def logout():
    for key in ("user", "match_view"):
        st.session_state.pop(key, None)


def load_samples():
    added = add_sample_data()
    st.session_state["sample_msg"] = (
        f"{added} sample items added" if added else "Sample data already added"
    )


tab_report, tab_match, tab_claims, tab_dup, tab_all, tab_profile = st.tabs(
    ["Report Item", "Find Matches", "Claims", "Duplicates", "All Items", "My Profile"]
)

# ====================== Tab 1: report an item ======================
with tab_report:
    if "report_msg" in st.session_state:
        st.success(st.session_state.pop("report_msg"))

    # These two are OUTSIDE the form on purpose: widgets inside a form do not
    # update the page until Submit, so the "Other" text box could not appear.
    item_type = st.radio("I want to report a", ["lost", "found"],
                         format_func=lambda x: f"{x.capitalize()} item", horizontal=True)
    category = st.selectbox("Category", CATEGORIES)
    other_type = ""
    if category == "Other":
        n = st.session_state.get("report_n", 0)   # changes after each save -> box is emptied
        other_type = st.text_input("What kind of item is it? (e.g. Umbrella, Helmet, Spectacles)",
                                   key=f"other_type_{n}")

    with st.form("report_form", clear_on_submit=True):
        title = st.text_input("Item name (e.g. Black leather wallet)")
        description = st.text_area("Description (colour, brand, marks, what is inside)")
        photo = st.file_uploader("Photo of the item (optional, helps the ML model match)",
                                 type=["jpg", "jpeg", "png"])
        location = st.selectbox("Where was it lost / found?", LOCATIONS)
        submitted = st.form_submit_button("Submit")

    if submitted:
        if not title.strip():
            st.error("Please enter the item name.")
        elif category == "Other" and not other_type.strip():
            st.error("You chose 'Other'. Please write what kind of item it is.")
        else:
            image_path = save_uploaded_image(photo) if photo else None
            if photo and image_path is None:
                st.error("That file is not a valid image. Please upload a JPG or PNG.")
            else:
                new_id = add_item(item_type, title.strip(), description.strip(),
                                  category, location, user_id=user_id,
                                  image_path=image_path,
                                  other_type=other_type.strip() or None)
                st.session_state["report_msg"] = f"Saved! Your item number is #{new_id}"
                st.session_state["report_n"] = st.session_state.get("report_n", 0) + 1
                st.rerun()

# ====================== Tab 2: find matches + claim ======================
with tab_match:
    lost_items = get_items("lost")
    found_items = get_items("found")

    if not lost_items:
        st.info("No lost items yet. Report one, or click 'Add sample data' in the sidebar.")
    else:
        labels = {}
        for i in lost_items:
            mine = " - yours" if i["user_id"] == user_id else ""
            labels[f"#{i['item_id']} - {i['title']} ({i['location']}){mine}"] = i
        choice = st.selectbox("Pick a lost item", list(labels))
        top_n = st.slider("How many matches to show?", 1, 10, 5)

        if st.button("Find matches"):
            lost = labels[choice]
            results = find_matches(lost, found_items, top_n=top_n)
            if results:
                save_matches(lost["item_id"], results)
            st.session_state["match_view"] = {"lost_id": lost["item_id"], "results": results}

        view = st.session_state.get("match_view")
        if view:
            lost = next((i for i in lost_items if i["item_id"] == view["lost_id"]), None)
            open_found_ids = {i["item_id"] for i in found_items}
            results = [m for m in view["results"] if m["item"]["item_id"] in open_found_ids]

            if lost is None:
                st.info("That lost item is no longer open.")
            elif not results:
                st.warning("No matching found items yet. Check again later.")
            else:
                st.markdown(f"Matches for **{lost['title']}**")
                show_photo(lost.get("image_path"), "Your lost item")
                for rank, m in enumerate(results, 1):
                    f = m["item"]
                    st.markdown(f"**#{rank}  {f['title']}** ({category_label(f)}) - found at {f['location']}")
                    show_photo(f.get("image_path"), "Found item")
                    st.progress(min(m["score"], 1.0), text=f"Match score: {m['score'] * 100:.0f}%")
                    st.caption("Why: " + m["reason"])

                    finder = get_user(f["user_id"])
                    if finder:
                        level = trust_level(get_reputation(finder["user_id"]))
                        st.caption(f"Reported by {finder['name']} - trust level: {level}")

                    if lost["user_id"] == user_id:
                        match_id = get_match_id(lost["item_id"], f["item_id"])
                        with st.expander("Claim this item"):
                            st.write("Verification question: " + question_for(f["category"]))
                            st.warning("You must also upload proof that it is yours: a photo or "
                                       "screenshot of the bill, receipt, warranty card or box.")
                            with st.form(f"claim_form_{match_id}"):
                                answer = st.text_area("Your answer")
                                proof = st.file_uploader("Proof of ownership (e.g. mobile bill)",
                                                         type=["jpg", "jpeg", "png"],
                                                         key=f"proof_{match_id}")
                                send = st.form_submit_button("Send claim")
                            if send:
                                ok, msg = create_claim(match_id, user_id, answer, proof)
                                if ok:
                                    st.success(msg)
                                else:
                                    st.error(msg)

# ====================== Tab 3: claims ======================
with tab_claims:
    st.subheader("Claims on items I found")
    pending = get_pending_claims_for_finder(user_id)
    if not pending:
        st.info("No pending claims.")
    for c in pending:
        level = trust_level(c["claimant_reputation"])
        st.markdown(f"**{c['found_title']}** - claimed by {c['claimant_name']} (trust: {level})")
        st.write("Question: " + c["question"])
        st.write("Their answer: " + c["answer"])
        if c.get("proof_path"):
            show_photo(c["proof_path"], "Proof uploaded by the claimant", width=400)
        else:
            st.caption("No proof was uploaded with this claim.")
        col1, col2 = st.columns(2)
        if col1.button("Approve", key=f"approve_{c['claim_id']}"):
            review_claim(c["claim_id"], True)
            st.rerun()
        if col2.button("Reject", key=f"reject_{c['claim_id']}"):
            review_claim(c["claim_id"], False)
            st.rerun()
        st.divider()

    st.subheader("My claims")
    my_claims = get_claims_by_claimant(user_id)
    if not my_claims:
        st.info("You have not claimed anything yet.")
    for c in my_claims:
        st.write(f"{c['found_title']} - **{c['status']}**")

# ====================== Tab 4: duplicates (Union-Find) ======================
with tab_dup:
    st.write("Repeated reports of the same item, grouped using Union-Find.")
    kind = st.radio("Check", ["lost", "found"], horizontal=True, key="dup_kind")
    items = get_items(kind)
    by_id = {i["item_id"]: i for i in items}
    groups = detect_duplicates(items)

    if not groups:
        st.success("No duplicates found.")
    for n, ids in enumerate(groups, 1):
        st.markdown(f"**Group {n}**")
        for item_id in ids:
            it = by_id[item_id]
            st.write(f"- #{item_id} {it['title']} ({it['location']})")

# ====================== Tab 5: all items ======================
with tab_all:
    rows = [
        {"id": i["item_id"], "type": i["item_type"], "title": i["title"],
         "category": category_label(i), "location": i["location"], "reported": i["reported_at"]}
        for i in get_items()
    ]
    if rows:
        st.dataframe(rows)
    else:
        st.info("Nothing here yet.")

# ====================== Tab 6: profile / reputation ======================
with tab_profile:
    score = get_reputation(user_id)
    st.subheader(user["name"])
    st.metric("Reputation score", f"{score} / 100")
    st.progress(min(max(score, 0), 100) / 100)
    st.write(f"Trust level: **{trust_level(score)}**")
    st.caption(
        f"+{FINDER_REWARD} when a claim on an item you found is approved. "
        f"{FALSE_CLAIM_PENALTY} when your claim is rejected. "
        f"Below {LOW_REPUTATION_LIMIT} you cannot make new claims."
    )
    log = get_reputation_log(user_id)
    if log:
        st.dataframe(log)
    else:
        st.info("No reputation changes yet.")

# ====================== Sidebar ======================
with st.sidebar:
    st.write(f"Logged in as **{user['name']}**")
    st.metric("Reputation", get_reputation(user_id))
    st.button("Logout", on_click=logout)
    st.divider()
    st.header("Demo")
    st.button("Add sample data", on_click=load_samples)
    if "sample_msg" in st.session_state:
        st.info(st.session_state.pop("sample_msg"))
    st.metric("Open lost items", len(get_items("lost")))
    st.metric("Open found items", len(get_items("found")))
    st.divider()
    st.caption("Text model: " + ("SBERT" if SBERT_AVAILABLE else "basic (SBERT not installed)"))
    st.caption("Photo model: " + ("MobileNetV2" if PHOTO_AVAILABLE else "off (torchvision not installed)"))