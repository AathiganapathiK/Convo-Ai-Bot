import React from "react";
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Legend,
  Tooltip
} from "recharts";
import { Cell } from "recharts";
import { formatValue } from "../../utils/format";


const COLORS = [
  "#4f46e5", // Indigo
  "#06b6d4", // Cyan
  "#10b981", // Emerald
  "#f59e0b", // Amber
  "#ec4899", // Pink
  "#8b5cf6", // Violet
  "#3b82f6", // Blue
  "#ef4444", // Red
  "#f97316", // Orange
  "#14b8a6"  // Teal
];

const PieChartView = ({ chart, data }) => {
  return (
    <ResponsiveContainer width="100%" height={350}>
      <PieChart>
        <Pie
          
          data={data}
          dataKey={chart.y_axis}
          nameKey={chart.x_axis}
          innerRadius={60}
          outerRadius={100}
          label={({ name, percent }) => {
            const pctVal = typeof percent === "number" && !isNaN(percent) ? (percent * 100).toFixed(0) : 0;
            return `${name} (${pctVal}%)`;
          }}
        >
          {data.map((entry, index) => (
            <Cell
              key={index}
              fill={COLORS[index % COLORS.length]}
            />
          ))}
        </Pie>
        <Legend />

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

      </PieChart>
    </ResponsiveContainer>
  );
};

export default PieChartView;