import React from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend
} from "recharts";

import {
  getAxisLabel,
  formatValue,
  formatAxisValue
} from "../../utils/format";



const BarChartView = ({ chart, data }) => {
  console.log("BAR LAYOUT:", chart?.layout);
  const isHorizontal = chart?.layout === "horizontal";

  return (
    <ResponsiveContainer width="100%" height={isHorizontal ? Math.max(350, data.length * 55) : 350}>
      <BarChart 
        data={data}
        layout={isHorizontal ? "vertical" : "horizontal"}
        margin={{ left: isHorizontal ? 20 : 25, right: 20, top: 20, bottom: 20 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
        {isHorizontal ? (
          <>
            <XAxis 
              type="number"
              stroke="var(--text-muted)"
              tickFormatter={(value) =>
                formatAxisValue(value, chart.y_axis)
              }
              label={{
                value: getAxisLabel(chart.y_axis_label || chart.y_axis, true),
                position: "insideBottom",
                offset: -5,
                fill: "var(--text-muted)"
              }}
            />
            <YAxis
              dataKey={chart.x_axis}
              type="category"
              width={200}
              stroke="var(--text-muted)"
              tick={{ fontSize: 12, fill: "var(--text-muted)" }}
              label={{
                value: getAxisLabel(chart.x_axis_label || chart.x_axis, false),
                angle: -90,
                position: "insideLeft",
                fill: "var(--text-muted)"
              }}
            />
          </>
        ) : (
          <>
            <XAxis
              dataKey={chart.x_axis}
              stroke="var(--text-muted)"
              label={{
                value: getAxisLabel(chart.x_axis_label || chart.x_axis, false),
                position: "insideBottom",
                offset: -5,
                fill: "var(--text-muted)"
              }}
              tick={{ fontSize: 12, fill: "var(--text-muted)" }} 
            />
            <YAxis
              width={80}
              stroke="var(--text-muted)"
              tickFormatter={(value) =>
                formatAxisValue(value, chart.y_axis)
              }
              label={{
                value: getAxisLabel(chart.y_axis_label || chart.y_axis, true),
                angle: -90,
                position: "insideLeft",
                fill: "var(--text-muted)"
              }}
            />
          </>
        )}

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
        {
          (chart.measures || [chart.y_axis]).map(
            (measure) => (
              <Bar
                fill="var(--chart-primary)"
                key={measure}
                dataKey={measure}
                name={
                  measure
                    .replace("Total", "")
                    .replace("_", " ")
                  
                }
              />
            )
          )
        }
      </BarChart>
    </ResponsiveContainer>
  );
};

export default BarChartView;