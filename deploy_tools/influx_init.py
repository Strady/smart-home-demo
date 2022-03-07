import influxdb

# Подключаемся
client = influxdb.InfluxDBClient(host='localhost', port=8086)
client.create_database('axiom_metrics')
client.switch_database('axiom_metrics')

# Создаем retention policies
client.query('CREATE RETENTION POLICY "hour" ON "axiom_metrics" DURATION 1h REPLICATION 1 SHARD DURATION 1h DEFAULT')
client.query('CREATE RETENTION POLICY "day" ON "axiom_metrics" DURATION 1d REPLICATION 1 SHARD DURATION 6h')
client.query('CREATE RETENTION POLICY "week" ON "axiom_metrics" DURATION 1w REPLICATION 1 SHARD DURATION 1d')
client.query('CREATE RETENTION POLICY "infinity" ON "axiom_metrics" DURATION 1000w REPLICATION 1 SHARD DURATION 1w')

# Создаем continuous queries
# 1) continues queries для суммирумых характеристик
for measurement in ('consumption', 'cost'):
    cq_minute = """
    CREATE CONTINUOUS QUERY "minute_{measurement}" ON "axiom_metrics" BEGIN
    SELECT SUM("value") AS "value" INTO "day"."{measurement}"
    FROM "axiom_metrics"."hour"."{measurement}"
    GROUP BY time(1m), *
    END
    """.format(measurement=measurement)

    client.query(cq_minute)

    cq_hour = """
    CREATE CONTINUOUS QUERY "hour_{measurement}" ON "axiom_metrics" BEGIN
    SELECT SUM("value") AS "value" INTO "week"."{measurement}"
    FROM "axiom_metrics"."day"."{measurement}"
    GROUP BY time(1h), *
    END
    """.format(measurement=measurement)

    client.query(cq_hour)

    cq_day = """
    CREATE CONTINUOUS QUERY "day_{measurement}" ON "axiom_metrics" 
    RESAMPLE EVERY 30m
    BEGIN
    SELECT SUM("value") AS "value" INTO "infinity"."{measurement}"
    FROM "axiom_metrics"."week"."{measurement}"
    GROUP BY time(1d), *
    END
    """.format(measurement=measurement)

    client.query(cq_day)


# 2) continues queries для характеристик, для которых вычисляется медианное значение
for measurement in ('current', 'voltage', 'frequency', 'active_power', 'reactive_power', 'temperature'):
    cq_minute = """
    CREATE CONTINUOUS QUERY "minute_{measurement}" ON "axiom_metrics" BEGIN
    SELECT MEDIAN("value") AS "value" INTO "day"."{measurement}"
    FROM "axiom_metrics"."hour"."{measurement}"
    GROUP BY time(1m), *
    END
    """.format(measurement=measurement)

    client.query(cq_minute)

    cq_hour = """
    CREATE CONTINUOUS QUERY "hour_{measurement}" ON "axiom_metrics" BEGIN
    SELECT MEDIAN("value") AS "value" INTO "week"."{measurement}"
    FROM "axiom_metrics"."day"."{measurement}"
    GROUP BY time(1h), *
    END
    """.format(measurement=measurement)

    client.query(cq_hour)

    cq_day = """
    CREATE CONTINUOUS QUERY "day_{measurement}" ON "axiom_metrics" 
    RESAMPLE EVERY 30m
    BEGIN
    SELECT MEDIAN("value") AS "value" INTO "infinity"."{measurement}"
    FROM "axiom_metrics"."week"."{measurement}"
    GROUP BY time(1d), *
    END
    """.format(measurement=measurement)

    client.query(cq_day)



