import { useParams } from "react-router-dom";
import { Placeholder } from "@/components/Placeholder";

export function OrderCreatePage() {
  const { id } = useParams<{ id: string }>();
  return <Placeholder title={`下单确认 #${id ?? "?"}`} note="商品摘要 + 券码 + 应付金额（T06 实现）。" />;
}
