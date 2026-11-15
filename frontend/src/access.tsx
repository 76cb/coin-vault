import { createContext, useContext } from "react";

/** Whether this login can change things (false for a read-only login). */
export const CanWrite = createContext(true);
export const useCanWrite = () => useContext(CanWrite);
