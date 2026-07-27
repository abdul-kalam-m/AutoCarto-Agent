"""Real-data connectors — Blueprint §6.1.

Each connector fetches one variable/measure for a set of Census tracts and
returns a plain ``{GEOID: value}`` dict (``None`` for missing/sentinel
values) — deliberately not a GeoDataFrame, since these connectors never
touch geometry; joining to ``data/atlanta_tracts_fulton_dekalb.geojson``
is the caller's job (see ``autocarto.real_data``).
"""
