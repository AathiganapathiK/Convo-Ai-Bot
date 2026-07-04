from sqlalchemy import text
from collections import defaultdict, deque
from database import engine


class RelationshipExpander:

    @staticmethod
    def expand(
        connection_id,
        tables
    ):

        if len(tables) <= 1:
            return tables

        graph = RelationshipExpander.build_graph(
            connection_id
        )

        expanded = set(tables)

        table_list = list(tables)

        for i in range(len(table_list)):

            for j in range(i + 1, len(table_list)):

                start = table_list[i]
                end = table_list[j]

                # Already directly connected
                if end in graph.get(start, set()):
                    continue

                # Find missing bridge tables
                bridges = (
                    RelationshipExpander.find_bridge_tables(
                        graph,
                        start,
                        end
                    )
                )

                expanded.update(bridges)

        return sorted(expanded)


    @staticmethod
    def build_graph(connection_id):

        query = """
        SELECT
            st_source.table_name,
            st_target.table_name
        FROM schema_relationships sr

        JOIN schema_tables st_source
            ON sr.source_table_id = st_source.table_id

        JOIN schema_tables st_target
            ON sr.target_table_id = st_target.table_id

        WHERE sr.connection_id = :connection_id
        """

        with engine.connect() as conn:

            rows = conn.execute(
                text(query),
                {
                    "connection_id": connection_id
                }
            ).fetchall()

        graph = defaultdict(set)

        for source, target in rows:

            graph[source].add(target)
            graph[target].add(source)

        return graph

    @staticmethod
    def find_bridge_tables(
        graph,
        start,
        end
    ):

        queue = deque([[start]])

        visited = {start}

        while queue:

            path = queue.popleft()

            current = path[-1]

            if current == end:

                return path[1:-1]

            for neighbour in graph.get(current, set()):

                if neighbour not in visited:

                    visited.add(neighbour)

                    queue.append(
                        path + [neighbour]
                    )

        return []