# Shortcuts for the common steps. Run `make help` to see them.

.PHONY: help install init load run app clean

help:
	@echo "make install   install the python dependencies"
	@echo "make init      create the warehouse table (and Postgres views)"
	@echo "make load      load the Goat Farm sample CSV into the warehouse"
	@echo "make run       build tree + iTOL files + render + chord for one tree"
	@echo "make app       open the request station and dashboard"
	@echo "make clean     remove generated outputs and the local SQLite file"

install:
	pip install -r requirements.txt

init:
	python -m src.db init

load:
	python -m src.etl data/goat_farm_proctor_creek.csv

run:
	python -m src.pipeline "Goat Farm - Proctor Creek"

app:
	streamlit run app/station.py

clean:
	rm -rf outputs/* revolving_kinship.db
