import { useParams } from "react-router-dom";
import { Placeholder } from "@/components/Placeholder";

export function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  return <Placeholder title={`商品详情 #${id ?? "?"}`} note="封面/预览媒体/价格/立即购买（T05 实现）。" />;
}
