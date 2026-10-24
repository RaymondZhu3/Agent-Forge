import { CalendarClock, Globe, MapPin, Newspaper, Receipt, ShoppingBag, Wallet, Wrench } from "lucide-react";

const ICONS: Record<string, typeof Wrench> = {
  serpapi_shopping: ShoppingBag,
  serpapi_news: Newspaper,
  serpapi_web_search: Globe,
  serpapi_local_places: MapPin,
  nessie_accounts: Wallet,
  nessie_purchases: Receipt,
  nessie_bills: CalendarClock,
};

export function toolTone(name: string): "search" | "banking" | "other" {
  return name.startsWith("serpapi_") ? "search" : name.startsWith("nessie_") ? "banking" : "other";
}

export default function ToolIcon({ name, size = 16 }: { name: string; size?: number }) {
  const Icon = ICONS[name] ?? Wrench;
  return (
    <span className={`tool-icon ${toolTone(name)}`} style={{ width: size + 14, height: size + 14 }}>
      <Icon size={size} />
    </span>
  );
}
