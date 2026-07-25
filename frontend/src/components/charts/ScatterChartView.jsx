import React from "react";
import { getAxisLabel, formatValue } from "../../utils/format";
import {
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend
} from "recharts";

const ScatterChartView = ({
  chart,
  data
}) => {

  return (
    <ResponsiveContainer
      width="100%"
      height={400}
    >

      <ScatterChart
        margin={{ left: 15, right: 20, top: 20, bottom: 20 }}
      >

        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />

        <XAxis
          dataKey={chart.x_axis}
          name={chart.x_axis}
          stroke="var(--text-muted)"
          tick={{ fontSize: 12, fill: "var(--text-muted)" }}
          label={{
            value: getAxisLabel(chart.x_axis_label || chart.x_axis, false),
            position: "insideBottom",
            offset: -5,
            fill: "var(--text-muted)"
          }}
        />

        <YAxis
          dataKey={chart.y_axis}
          name={chart.y_axis}
          stroke="var(--text-muted)"
          tickFormatter={(value) =>
            formatValue(value, chart.y_axis)
          }
          tick={{ fontSize: 12, fill: "var(--text-muted)" }}
          label={{
            value: getAxisLabel(chart.y_axis_label || chart.y_axis, true),
            angle: -90,
            position: "insideLeft",
            fill: "var(--text-muted)"
          }}
        />

        <Tooltip
          formatter={(value, name) => [
            formatValue(value, name),
            name
          ]}
          contentStyle={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border-color)",
            color: "var(--text-main)",
            borderRadius: "8px"
          }}
        />

        <Legend />

        <Scatter
          name={chart.title}
          data={data}
          fill="var(--chart-primary)"
        />

      </ScatterChart>

    </ResponsiveContainer>
  );
};

export default ScatterChartView;