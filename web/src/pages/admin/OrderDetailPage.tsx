import { useParams } from "react-router-dom";
import { Placeholder } from "@/components/Placeholder";

export function AdminOrderDetailPage() {
  const { id } = useParams<{ id: string }>();
  return <Placeholder title={`订单详情 #${id ?? "?"}`} note="全字段 + 核销/撤销 + 下载日志（T06 实现）。" />;
}
