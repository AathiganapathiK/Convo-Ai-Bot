class RuntimeContextBuilder:

    @staticmethod
    def build(metadata_result):
        """
        Builds a compact semantic runtime context
        for PromptBuilder.
        """

        lines = []

        # --------------------------------------------------
        # TABLES
        # --------------------------------------------------

        lines.append("=== RESOLVED TABLES ===")

        for table in metadata_result.get("tables", []):

            bridge = "Yes" if table.get("is_bridge") else "No"

            lines.append(
                f"- {table['table_name']} "
                f"(score={table['score']}, bridge={bridge})"
            )


        # --------------------------------------------------
        # COLUMNS
        # --------------------------------------------------

        lines.append("")
        lines.append("=== AVAILABLE COLUMNS ===")

        for table in metadata_result.get("tables", []):

            lines.append("")
            lines.append(table["table_name"])

            for col in table["columns"]:

                dtype = col["data_type"]

                flags = []

                if col["is_primary_key"]:
                    flags.append("PK")

                if col["is_foreign_key"]:
                    flags.append("FK")

                flag_text = ""

                if flags:
                    flag_text = f" [{' '.join(flags)}]"

                lines.append(

                    f"  - {col['column_name']} "
                    f"({dtype})"
                    f"{flag_text}"

                )

        return "\n".join(lines)