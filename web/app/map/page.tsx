import type { Metadata } from "next";
import { MapApp } from "@/components/map/MapApp";

export const metadata: Metadata = { title: "Map" };

export default function MapPage() {
  return <MapApp />;
}
