import React from "react";
import { getAxisLabel, formatValue, formatAxisValue } from "../../utils/format";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip
} from "recharts";


const LineChartView = ({ chart, data }) => {
  console.log("CHART:", chart);
  console.log("MEASURES:", chart?.measures);

  return (
    <ResponsiveContainer width="100%" height={350}>
      <LineChart 
        data={data}
        margin={{ left: 25, right: 20, top: 20, bottom: 20 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
        <XAxis
          dataKey={chart.x_axis}
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
          width={80}
          stroke="var(--text-muted)"
          tickFormatter={(value) =>
            formatAxisValue(value, chart.y_axis)
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
        {
          (chart.measures || [chart.y_axis]).map(
            (measure) => (
              <Line
                key={measure}
                dataKey={measure}
                stroke="var(--chart-primary)"
                strokeWidth={2}
                name={
                  measure
                    .replace("Total", "")
                    .replace("_", " ")
                }
              />
            )
          )
        }
      </LineChart>
    </ResponsiveContainer>

  );

};



export default LineChartView;