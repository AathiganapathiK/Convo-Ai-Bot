import React from "react";
import { Table } from "antd";

const TableView = ({ data }) => {
  if (!data?.length) return null;

  const columns = Object.keys(
    data[0]
  ).map((key) => ({
    title: key === "" ? "Value" : key,
    dataIndex: key,
    key,
    render: (val, record) => {
      const cellVal = record[key];
      if (cellVal === null || cellVal === undefined) return "-";
      if (typeof cellVal === "object") return JSON.stringify(cellVal);
      return String(cellVal);
    }
  }));

  const tableData = data.map(
    (row, index) => ({
      key: index,
      ...row,
    })
  );

  return (
    <Table
      columns={columns}
      dataSource={tableData}
      pagination={{
        pageSize: 10,
      }}
      scroll={{ x: true }}
    />
  );
};

export default TableView;