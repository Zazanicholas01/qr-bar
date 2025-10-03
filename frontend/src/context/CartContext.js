import React, { createContext, useContext, useMemo, useReducer } from "react";

const CartContext = createContext(null);

const initialState = {
  items: [],
};

function cartReducer(state, action) {
  switch (action.type) {
    case "ADD_ITEM": {
      const { item, quantity } = action.payload;
      const existing = state.items.find(line => line.id === item.id);

      if (existing) {
        return {
          ...state,
          items: state.items.map(line =>
            line.id === item.id
              ? { ...line, quantity: line.quantity + quantity }
              : line
          ),
        };
      }

      return {
        ...state,
        items: [
          ...state.items,
          {
            ...item,
            quantity,
          },
        ],
      };
    }

    case "UPDATE_QUANTITY": {
      const { productId, quantity } = action.payload;
      if (quantity <= 0) {
        return {
          ...state,
          items: state.items.filter(line => line.id !== productId),
        };
      }

      return {
        ...state,
        items: state.items.map(line =>
          line.id === productId ? { ...line, quantity } : line
        ),
      };
    }

    case "REMOVE_ITEM": {
      const { productId } = action.payload;
      return {
        ...state,
        items: state.items.filter(line => line.id !== productId),
      };
    }

    case "CLEAR":
      return { items: [] };

    default:
      return state;
  }
}

function CartProvider({ children }) {
  const [state, dispatch] = useReducer(cartReducer, initialState);

  const addItem = (item, quantity = 1) => {
    const safeQuantity = Number.isFinite(quantity)
      ? Math.max(1, Math.floor(quantity))
      : 1;
    dispatch({ type: "ADD_ITEM", payload: { item, quantity: safeQuantity } });
  };

  const updateQuantity = (productId, quantity) => {
    const nextQuantity = Number.isFinite(quantity) ? Math.floor(quantity) : 0;
    dispatch({ type: "UPDATE_QUANTITY", payload: { productId, quantity: nextQuantity } });
  };

  const removeItem = productId => {
    dispatch({ type: "REMOVE_ITEM", payload: { productId } });
  };

  const clearCart = () => dispatch({ type: "CLEAR" });

  const totals = useMemo(
    () =>
      state.items.reduce(
        (acc, line) => {
          acc.quantity += line.quantity;
          acc.amount += line.quantity * line.price;
          return acc;
        },
        { quantity: 0, amount: 0 }
      ),
    [state.items]
  );

  const { quantity: totalQuantity, amount: totalAmount } = totals;

  const value = useMemo(
    () => ({
      items: state.items,
      addItem,
      updateQuantity,
      removeItem,
      clearCart,
      totalQuantity,
      totalAmount,
    }),
    [state.items, totalQuantity, totalAmount]
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

function useCart() {
  const context = useContext(CartContext);
  if (!context) {
    throw new Error("useCart must be used within a CartProvider");
  }
  return context;
}

export { CartProvider, useCart };
