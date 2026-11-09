# FindrAlgo - Smart Lost and Found Matching System

Matches lost and found items on campus using DSA (Union-Find, Heap, Hash Map) + ML/NLP (SBERT, CNN, Random Forest).

## Run
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python db_setup.py
streamlit run app.py
```

## Status
Scaffold done. Next: union_find.py, matching_engine.py.
