import React from "react";
import { getAxisLabel } from "../../utils/format";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip
} from "recharts";

export const formatNumber = (value) =>
  new Intl.NumberFormat(
    "en-US",
    {
      notation: "compact",
      maximumFractionDigits: 2
    }
  ).format(value);

const LineChartView = ({ chart, data }) => {
  console.log("CHART:", chart);
  console.log("MEASURES:", chart?.measures);

  return (
    <ResponsiveContainer width="100%" height={350}>
      <LineChart 
        data={data}
        margin={{ left: 15, right: 20, top: 20, bottom: 20 }}
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
          stroke="var(--text-muted)"
          tick={{ fontSize: 12, fill: "var(--text-muted)" }}
          label={{  
            value: getAxisLabel(chart.y_axis_label || chart.y_axis, true),
            angle: -90,
            position: "insideLeft",
            fill: "var(--text-muted)"
          }}
        />

        <Tooltip
          formatter={(value) => formatNumber(value)}
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